"""
Assinatura digital do XML NF-e com certificado A1 (.pfx).

Algoritmos conforme NT 2011/004 e manual NF-e 4.0:
  - Digest:    SHA-256
  - Signature: RSA-SHA-256
  - C14N:      http://www.w3.org/TR/2001/REC-xml-c14n-20010315
  - Transform: enveloped-signature

O elemento assinado é <infNFe> pelo seu atributo Id="NFe...".
"""

import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.x509 import Certificate
from lxml import etree
import base64
import hashlib

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_NS = "http://www.portalfiscal.inf.br/nfe"
_XMLDSIG = "http://www.w3.org/2000/09/xmldsig#"
_C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
_ENV_SIG = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
_RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
_SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"


def _c14n(element: etree._Element) -> bytes:
    """Canonicalização C14N do elemento (sem comentários)."""
    return etree.tostring(element, method="c14n", exclusive=False, with_comments=False)


def _digest_sha256(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


class NfeSigner:
    """
    Assina o XML NF-e com certificado A1 (PKCS#12 / .pfx).
    Produz XML com <Signature> embutida conforme XMLDSig.
    """

    def __init__(self) -> None:
        self._private_key = None
        self._cert_pem: bytes | None = None
        self._loaded = False

    def _load_certificate(self) -> None:
        if self._loaded:
            return

        cert_path = Path(settings.CERT_PATH)
        if not cert_path.exists():
            logger.warning("certificado_nao_encontrado", path=str(cert_path))
            self._loaded = True
            return

        from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates

        pfx_data = cert_path.read_bytes()
        password = settings.CERT_PASSWORD.encode() if settings.CERT_PASSWORD else None

        private_key, certificate, _ = load_key_and_certificates(pfx_data, password)
        self._private_key = private_key
        self._cert_pem = certificate.public_bytes(serialization.Encoding.DER)
        self._loaded = True
        logger.info("certificado_carregado", subject=str(certificate.subject))

    def sign(self, xml_string: str) -> str:
        """
        Recebe o XML sem assinatura e retorna com <Signature> embutida.
        Se o certificado não estiver disponível (ex.: ambiente de teste),
        retorna o XML com uma assinatura placeholder para não bloquear o fluxo.
        """
        self._load_certificate()

        root = etree.fromstring(xml_string.encode("utf-8"))
        inf_nfe = root.find(f"{{{_NS}}}infNFe")

        if inf_nfe is None:
            raise ValueError("Elemento infNFe não encontrado no XML")

        ref_id = inf_nfe.get("Id", "")

        if self._private_key is None:
            logger.warning("assinatura_placeholder", motivo="certificado_ausente")
            return self._inject_placeholder_signature(root, ref_id)

        # 1. Canonicalizar o infNFe e calcular digest
        c14n_bytes = _c14n(inf_nfe)
        digest_value = _digest_sha256(c14n_bytes)

        # 2. Montar SignedInfo canônico
        signed_info_elem = self._build_signed_info(ref_id, digest_value)
        c14n_signed_info = _c14n(signed_info_elem)

        # 3. Assinar com chave privada RSA-SHA256
        signature_bytes = self._private_key.sign(
            c14n_signed_info,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        signature_value = base64.b64encode(signature_bytes).decode()

        # 4. Montar elemento Signature completo
        signature_elem = self._build_signature_element(
            signed_info_elem, signature_value, ref_id, digest_value
        )
        root.append(signature_elem)

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8").decode("utf-8")

    def _build_signed_info(
        self, ref_id: str, digest_value: str
    ) -> etree._Element:
        ns = _XMLDSIG
        si = etree.Element(f"{{{ns}}}SignedInfo")
        cm = etree.SubElement(si, f"{{{ns}}}CanonicalizationMethod", Algorithm=_C14N)
        sm = etree.SubElement(si, f"{{{ns}}}SignatureMethod", Algorithm=_RSA_SHA256)
        ref = etree.SubElement(si, f"{{{ns}}}Reference", URI=f"#{ref_id}")
        transforms = etree.SubElement(ref, f"{{{ns}}}Transforms")
        etree.SubElement(transforms, f"{{{ns}}}Transform", Algorithm=_ENV_SIG)
        etree.SubElement(transforms, f"{{{ns}}}Transform", Algorithm=_C14N)
        dm = etree.SubElement(ref, f"{{{ns}}}DigestMethod", Algorithm=_SHA256)
        dv = etree.SubElement(ref, f"{{{ns}}}DigestValue")
        dv.text = digest_value
        return si

    def _build_signature_element(
        self,
        signed_info_elem: etree._Element,
        signature_value: str,
        ref_id: str,
        digest_value: str,
    ) -> etree._Element:
        ns = _XMLDSIG
        sig = etree.Element(f"{{{ns}}}Signature")
        sig.append(signed_info_elem)

        sv = etree.SubElement(sig, f"{{{ns}}}SignatureValue")
        sv.text = signature_value

        ki = etree.SubElement(sig, f"{{{ns}}}KeyInfo")
        x509_data = etree.SubElement(ki, f"{{{ns}}}X509Data")
        x509_cert = etree.SubElement(x509_data, f"{{{ns}}}X509Certificate")
        x509_cert.text = base64.b64encode(self._cert_pem).decode() if self._cert_pem else ""

        return sig

    def _inject_placeholder_signature(
        self, root: etree._Element, ref_id: str
    ) -> str:
        """Assinatura inválida para uso exclusivo em homologação/testes."""
        ns = _XMLDSIG
        sig = etree.SubElement(root, f"{{{ns}}}Signature")
        etree.SubElement(sig, f"{{{ns}}}SignatureValue").text = "PLACEHOLDER_SEM_CERTIFICADO"
        ki = etree.SubElement(sig, f"{{{ns}}}KeyInfo")
        etree.SubElement(ki, f"{{{ns}}}X509Data")
        return etree.tostring(root, xml_declaration=True, encoding="UTF-8").decode("utf-8")


nfe_signer = NfeSigner()

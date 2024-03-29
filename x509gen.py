#!/usr/bin/python3

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding, PrivateFormat, PublicFormat, NoEncryption,
    load_pem_private_key, load_pem_public_key)
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
import datetime

ROOT_DN = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, 'Mothership Root'),
])

INTERMEDIATE_DN = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, 'Mothership CA1'),
])

SERVER_DN = x509.Name([
    # By convention, only DNS names are allowed in the common name.
    # See e.g. cabforum baseline requirements 7.1.4.2.2.a
    x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, 'Mothership Server'),
])

CLIENT_DN = x509.Name([
    # By convention, only DNS names are allowed in the common name.
    # See e.g. cabforum baseline requirements 7.1.4.2.2.a
    x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, 'Random client'),
])

BACKEND = default_backend()

# cabforum baseline requirements 7.1.2.1.b, 7.1.2.2.e
CA_KEYUSAGE = x509.KeyUsage(
    digital_signature=True,
    content_commitment=False,
    key_encipherment=False,
    data_encipherment=False,
    key_agreement=False,
    key_cert_sign=True,
    crl_sign=True,
    encipher_only=False,
    decipher_only=False,
)

# cabforum baseline requirements 7.1.2.3.
ENTITY_KEYUSAGE = x509.KeyUsage(
    digital_signature=True,
    content_commitment=False,
    key_encipherment=True,
    data_encipherment=False,
    key_agreement=False,
    key_cert_sign=False,
    crl_sign=False,
    encipher_only=False,
    decipher_only=False,
)

# Self-signed entity needs the union of CA and entity flags.
SELFSIGNED_ENTITY_KEYUSAGE = x509.KeyUsage(
    digital_signature=True,
    content_commitment=False,
    key_encipherment=True,
    data_encipherment=False,
    key_agreement=False,
    key_cert_sign=True,
    crl_sign=False,
    encipher_only=False,
    decipher_only=False,
)

SERVER_EXTKEYUSAGE = x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH])
CLIENT_EXTKEYUSAGE = x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH])

def create_rsa_key_pair():
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=BACKEND
    )
    public_key = private_key.public_key()
    priv_bytes = private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    pub_bytes = public_key.public_bytes(Encoding.PEM, PublicFormat.PKCS1)
    return priv_bytes, pub_bytes

def _cert_helper(public_key, subject_dn, issuer_dn, days):
    builder = x509.CertificateBuilder()
    builder = builder.subject_name(subject_dn)
    builder = builder.issuer_name(issuer_dn)

    validity_start = datetime.datetime.now()
    validity_end = validity_start + datetime.timedelta(days, 0, 0)

    builder = builder.not_valid_before(validity_start)
    builder = builder.not_valid_after(validity_end)
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(public_key)
    return builder

def create_root_cert(pem_private_key, days):
    private_key = load_pem_private_key(pem_private_key, None, BACKEND)
    # A root certificate is self-signed, so the public and private keys
    # are from the same key pair
    public_key = private_key.public_key()

    builder = _cert_helper(public_key,
                           subject_dn=ROOT_DN,
                           issuer_dn=ROOT_DN,
                           days=days)

    # FIXME: does a root CA cert get a SAN?

    builder = builder.add_extension(
        # Root certificates do not get a path length.
        x509.BasicConstraints(ca=True, path_length=None), critical=True,
    )
    builder = builder.add_extension(CA_KEYUSAGE, critical=True)
    builder = builder.add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(public_key),
        critical=False
    )
    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(public_key),
        critical=False
    )

    certificate = builder.sign(
        private_key=private_key, algorithm=hashes.SHA256(),
        backend=BACKEND
    )
    cert_bytes = certificate.public_bytes(Encoding.PEM)
    return cert_bytes

def create_signing_cert(pem_issuer_cert, pem_private_key, pem_public_key, days):
    issuer_cert = x509.load_pem_x509_certificate(pem_issuer_cert, BACKEND)
    private_key = load_pem_private_key(pem_private_key, None, BACKEND)
    public_key = load_pem_public_key(pem_public_key, BACKEND)

    builder = _cert_helper(public_key,
                           subject_dn=INTERMEDIATE_DN,
                           issuer_dn=issuer_cert.subject,
                           days=days)

    builder = builder.add_extension(
        x509.BasicConstraints(ca=True, path_length=0), critical=True,
    )
    builder = builder.add_extension(CA_KEYUSAGE, critical=True)

    builder = builder.add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_cert.public_key()),
        critical=False
    )
    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(public_key),
        critical=False
    )

    certificate = builder.sign(
        private_key=private_key, algorithm=hashes.SHA256(),
        backend=BACKEND
    )
    cert_bytes = certificate.public_bytes(Encoding.PEM)
    return cert_bytes


def create_server_cert(pem_issuer_cert, pem_private_key, pem_public_key, days):
    issuer_cert = x509.load_pem_x509_certificate(pem_issuer_cert, BACKEND)
    private_key = load_pem_private_key(pem_private_key, None, BACKEND)
    public_key = load_pem_public_key(pem_public_key, BACKEND)

    # FIXME: use a CSR to acquire subject & SAN?

    builder = _cert_helper(public_key,
                           subject_dn=SERVER_DN,
                           issuer_dn=issuer_cert.subject,
                           days=days)

    builder = builder.add_extension(
        x509.SubjectAlternativeName(
            [x509.DNSName(u'mothership_server')]
        ),
        critical=True
    )
    builder = builder.add_extension(
        x509.BasicConstraints(ca=False, path_length=None), critical=True,
    )
    builder = builder.add_extension(ENTITY_KEYUSAGE, critical=True)
    builder = builder.add_extension(SERVER_EXTKEYUSAGE, critical=True)
    builder = builder.add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_cert.public_key()),
        critical=False
    )
    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(public_key),
        critical=False
    )

    certificate = builder.sign(
        private_key=private_key, algorithm=hashes.SHA256(),
        backend=BACKEND
    )

    cert_bytes = certificate.public_bytes(Encoding.PEM)
    return cert_bytes

def create_selfsigned_client_cert(pem_private_key, days):
    private_key = load_pem_private_key(pem_private_key, None, BACKEND)
    public_key = private_key.public_key()

    # FIXME: use a CSR to acquire subject & SAN?

    builder = _cert_helper(public_key,
                           subject_dn=CLIENT_DN,
                           issuer_dn=CLIENT_DN,
                           days=days)

    device_name = x509.Name([
        x509.NameAttribute(NameOID.SERIAL_NUMBER, 'device_0001'),
    ])

    builder = builder.add_extension(
        x509.SubjectAlternativeName(
            [x509.DirectoryName(device_name)]
        ),
        critical=True
    )
    builder = builder.add_extension(
        x509.BasicConstraints(ca=False, path_length=None), critical=True,
    )
    builder = builder.add_extension(SELFSIGNED_ENTITY_KEYUSAGE, critical=True)
    builder = builder.add_extension(CLIENT_EXTKEYUSAGE, critical=True)
    builder = builder.add_extension(
        x509.AuthorityKeyIdentifier.from_issuer_public_key(public_key),
        critical=False
    )
    builder = builder.add_extension(
        x509.SubjectKeyIdentifier.from_public_key(public_key),
        critical=False
    )

    certificate = builder.sign(
        private_key=private_key, algorithm=hashes.SHA256(),
        backend=BACKEND
    )

    cert_bytes = certificate.public_bytes(Encoding.PEM)
    return cert_bytes

def main():
    try:
        root_ca_priv_key = open('root_ca_priv_key.pem', 'rb').read()
        root_ca_pub_key = open('root_ca_pub_key.pem', 'rb').read()
        print('read root CA keys.')
    except FileNotFoundError:
        print('Creating new root keys.')
        root_ca_priv_key, root_ca_pub_key = create_rsa_key_pair()
        open('root_ca_priv_key.pem', 'wb').write(root_ca_priv_key)
        open('root_ca_pub_key.pem', 'wb').write(root_ca_pub_key)

    try:
        root_cert = open('root_cert.pem', 'rb').read()
        print('read root certificate.')
    except FileNotFoundError:
        print('Creating new root certificate.')
        root_cert = create_root_cert(root_ca_priv_key, 365)
        open('root_cert.pem', 'wb').write(root_cert)
        # FIXME: new root cert will require us to regenerate all downstream certs.

    try:
        signing_ca_priv_key = open('signing_ca_priv_key.pem', 'rb').read()
        signing_ca_pub_key = open('signing_ca_pub_key.pem', 'rb').read()
        print('read signing keys.')
    except FileNotFoundError:
        print('Creating new signing CA keys.')
        signing_ca_priv_key, signing_ca_pub_key = create_rsa_key_pair()
        open('signing_ca_priv_key.pem', 'wb').write(signing_ca_priv_key)
        open('signing_ca_pub_key.pem', 'wb').write(signing_ca_pub_key)
    try:
        signing_cert = open('signing_cert.pem', 'rb').read()
        print('read signing certificate.')
    except FileNotFoundError:
        print('Creating new signing certificate.')
        signing_cert = create_signing_cert(root_cert, root_ca_priv_key, signing_ca_pub_key, 14)
        open('signing_cert.pem', 'wb').write(signing_cert)

    try:
        server_priv_key = open('server_priv_key.pem', 'rb').read()
        server_pub_key = open('server_pub_key.pem', 'rb').read()
        print('read server keys.')
    except FileNotFoundError:
        print('Creating new server keys.')
        server_priv_key, server_pub_key = create_rsa_key_pair()
        open('server_priv_key.pem', 'wb').write(server_priv_key)
        open('server_pub_key.pem', 'wb').write(server_pub_key)

        # FIXME: new keys require a new cert as well.
    try:
        server_cert = open('server_cert.pem', 'rb').read()
        print('read server certificate.')
    except FileNotFoundError:
        print('Creating new server certificate.')
        server_cert = create_server_cert(signing_cert, signing_ca_priv_key, server_pub_key, 14)
        open('server_cert.pem', 'wb').write(server_cert)

    try:
        client_priv_key = open('client_priv_key.pem', 'rb').read()
        client_pub_key = open('client_pub_key.pem', 'rb').read()
        print('read client keys.')
    except FileNotFoundError:
        print('Creating new client keys.')
        client_priv_key, client_pub_key = create_rsa_key_pair()
        open('client_priv_key.pem', 'wb').write(client_priv_key)
        open('client_pub_key.pem', 'wb').write(client_pub_key)

        # FIXME: new keys require a new cert as well.
    try:
        client_cert = open('client_cert.pem', 'rb').read()
        print('read client certificate.')
    except FileNotFoundError:
        print('Creating new client certificate.')
        client_cert = create_selfsigned_client_cert(client_priv_key, 14)
        open('client_cert.pem', 'wb').write(client_cert)


main()

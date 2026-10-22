# Security

This project defaults to localhost and is designed for a single trusted operator. It does not supply authentication, tenant isolation, or a secure document-upload service. Do not expose it publicly without authenticated TLS ingress and request limits.

Treat indexed documents and generated storage as private. Retrieved text is sent to your configured model provider. Parsing untrusted files is not risk-free; time/size limits are not an OS sandbox. Stored index checksums detect accidental corruption, not malicious tampering by someone who can rewrite the whole storage directory.

Do not include secrets or sensitive documents in public issues. Report security concerns through the maintainer's GitHub contact options; describe the impact without publishing credentials or private data.

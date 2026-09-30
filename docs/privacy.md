# Privacy statement

CareCost's public data pipeline downloads and stores public hospital pricing records. Its private bill checker runs OCR and an open-weight language model on the machine hosting the app. It does not call an outside AI company with bill text.

**Local app:** the browser, application, OCR and Ollama can run on the patient's own computer. **Hosted app:** uploads travel to and are processed on the hosting server. Saying the bill never leaves the patient's device would be false in that deployment.

The application does not intentionally write uploaded files, extracted text, line items or bill findings to disk, database, application logs or shared caches. Uploaded bytes and text remain in framework/session memory while in use. Tesseract is piped through stdin/stdout; PDF rendering is memory based. Extraction errors are shown without raw bill text or exception payloads. Downloading the review deliberately writes bill details to the user's browser download location.

Use **Clear bill and review** to remove this application's session references and reset the upload widget. Closing a browser is not guaranteed to end the server session immediately. Clearing is not cryptographic erasure: framework buffers, process memory, swap, crash reports or infrastructure outside this code can retain data temporarily. No HIPAA-compliance certification is claimed.

Streamlit usage telemetry is disabled. Model weights may be downloaded once through an explicit setup script with no patient content. Runtime embedding loads use local-only files. Ollama requests go to numeric loopback, do not use environment proxies, do not follow redirects, verify that model metadata describes local weights rather than a remote/cloud model before sending bill text, and request model unloading after each call. Run Ollama with `OLLAMA_NO_CLOUD=1` for defense in depth. Ollama and the operating system remain independent components; configure their logging and access appropriately.

The comparison map requests public map tiles from CARTO when a price comparison is displayed. It sends the map view and public hospital coordinates, not bill text. The starting-area choice is an approximate town center, not a device location. Directions open Google Maps only when clicked. Price-source links open public hospital websites. These external services may receive ordinary browser/network metadata.

Before serving real users, review authentication, TLS, per-session isolation, reverse-proxy request logging, infrastructure access, operating-system swap, backups, retention, subprocess timeouts and resource exhaustion. Use de-identified synthetic bills for demos and research until that review is complete. Do not commit real bills, screenshots of real bills, tokens or credentials to this repository.

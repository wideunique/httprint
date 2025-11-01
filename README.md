# HTTPrint

A very simple web interface to upload and print files.


## Install and run

Dependencies:
* Python 3
* **pdfinfo** executable (package: **poppler-utils**)
* **lp** command (CUPS client) available in PATH

Recommended (virtualenv):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Configure the service editing `config.yaml` (or another file pointed by the
`HTTPRINT_CONFIG` environment variable), then run:
```bash
./httprint.py
```

Now you can **point your browser to [http://localhost:7777/](http://localhost:7777/)**

You can also **run the server in https**, putting in the *ssl* directory two files named *httprint_key.pem* and *httprint_cert.pem*

### Configuration

All runtime settings now live in YAML. The default file is `config.yaml` in the
repository root; set `HTTPRINT_CONFIG` to override the location. Example:

```yaml
port: 7777
queue_dir: queue
archive: true
print_cmd: "lp -n %(copies)s -o sides=%(sides)s -o media=%(media)s"
ip_whitelist:
  - 127.0.0.1/32
  - 192.168.5.0/24
auth_username: printer
auth_password: s3cret
```

Clients whose IP falls inside an entry listed in `ip_whitelist` bypass Basic
authentication. Everyone else must authenticate with the configured
`auth_username`/`auth_password` pair.

Default values (override them in the YAML file):

* **print_with_code** is true, and the uploaded files are just scheduled for priting. To actually print them, you should supply the generated code, for example: `curl -X POST http://localhost:7777/api/print/1234`
* **max_pages** is set to 10, limiting the number of allowed copies
* **pdf_only** is true, meaning that only PDF files are allowed
* **check_pdf_pages** is true, and the number of pages of a PDF are taken into consideration, calculating the maximum number of pages to print

See `config.yaml` for the complete list of switches and their defaults.

Once a document is queued, it can be made persistent creating an empty file *code-docname.pdf.keep* in the *queue* directory.

### Partial printing

Uploads (including the web UI) may specify an optional `pages` field using a
comma-separated list of page numbers and ranges (for example `1-3,5`). The value
gets validated against the PDF's total page count and, when present, HTTPrint
invokes the underlying print command with `-o page-ranges=...`. Leaving it blank
prints the entire document.

### Running with systemd

1. Create a dedicated user and deployment directory:
   ```bash
   sudo useradd --system --home /opt/httprint --shell /usr/sbin/nologin httprint
   sudo mkdir -p /opt/httprint
   sudo chown httprint:httprint /opt/httprint
   ```
2. Deploy the application (for example via git) into `/opt/httprint`, set up the virtualenv, and copy `config.example.yaml` to `/etc/httprint/config.yaml` editing credentials and paths as needed.
3. Install the service unit and optional environment overrides:
   ```bash
   sudo cp systemd/httprint.service /etc/systemd/system/httprint.service
   sudo mkdir -p /etc/httprint
   sudo cp systemd/httprint.env.example /etc/httprint/httprint.env
   ```
   Adjust `/etc/httprint/httprint.env` to point `APP_ROOT`, `PYTHON_BIN`, and `HTTPRINT_CONFIG` to the right locations.
4. Reload systemd and enable the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now httprint.service
   ```
5. Check status and logs:
   ```bash
   sudo systemctl status httprint.service
   journalctl -u httprint.service -f
   ```

## Development & Tests

Install dev deps and run tests (pytest):
```bash
pip install -r requirements-dev.txt
pytest -q
```

CI runs on GitHub Actions for Python 3.10–3.12 and executes the same pytest command.


# License and copyright

Copyright 2019 Davide Alberani <da@mimante.net>

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

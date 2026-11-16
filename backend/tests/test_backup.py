"""Export all data to a zip file and import it again."""

import io
import json
import zipfile

from tests.listing_samples import HEMNET_STYLE
from tests.report_factory import make_report_pdf
from tests.uploads import upload_pdf


def export(client) -> bytes:
    response = client.get("/api/backup")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    return response.content


def import_(client, content: bytes):
    return client.post("/api/backup", content=content, headers={"content-type": "application/zip"})


def zip_of(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_export_then_import_restores_everything(client):
    pdf = make_report_pdf()
    document = upload_pdf(client, pdf).json()
    client.post("/api/properties/from-text", json={"text": HEMNET_STYLE})
    backup = export(client)

    client.delete(f"/api/cooperatives/{document['cooperative_id']}")
    client.post("/api/properties/from-text", json={"text": HEMNET_STYLE})
    assert client.get("/api/cooperatives").json() == []

    assert import_(client, backup).status_code == 204
    [cooperative] = client.get("/api/cooperatives").json()
    assert cooperative["name"] == "Brf Provhuset"
    assert len(client.get("/api/properties").json()) == 1
    assert client.get(f"/api/documents/{document['id']}/file").content == pdf


def test_export_contains_manifest_database_and_documents(client):
    upload_pdf(client, make_report_pdf())
    with zipfile.ZipFile(io.BytesIO(export(client))) as archive:
        names = archive.namelist()
        assert json.loads(archive.read("manifest.json"))["app"] == "boster"
    assert "boster.db" in names
    assert any(name.startswith("documents/") and name.endswith(".pdf") for name in names)


def test_rejects_files_that_are_not_exports(client):
    upload_pdf(client, make_report_pdf())
    for content in (b"not a zip", zip_of({"hello.txt": b"hi"}),
                    zip_of({"manifest.json": b'{"app": "other", "format": 1}', "boster.db": b""}),
                    zip_of({"manifest.json": b'{"app": "boster", "format": 1}', "boster.db": b"not sqlite"})):
        response = import_(client, content)
        assert response.status_code == 422, content[:40]
    assert len(client.get("/api/cooperatives").json()) == 1  # Nothing was replaced.


def test_rejects_unexpected_paths_in_the_zip(client):
    backup = export(client)
    with zipfile.ZipFile(io.BytesIO(backup)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files["documents/../../escape.pdf"] = b"%PDF-"
    response = import_(client, zip_of(files))
    assert response.status_code == 422
    assert "okända" in response.json()["detail"]


def test_rejects_exports_from_a_newer_version(client):
    backup = export(client)
    with zipfile.ZipFile(io.BytesIO(backup)) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    files["manifest.json"] = b'{"app": "boster", "format": 99}'
    assert "nyare version" in import_(client, zip_of(files)).json()["detail"]

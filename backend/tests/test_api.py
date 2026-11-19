import io
import os
import tempfile
os.environ["DATA_DIR"]=tempfile.mkdtemp(prefix="imagetrace-tests-")
os.environ["APP_API_KEY"]="test-key-at-least-16-chars"
from fastapi.testclient import TestClient
from PIL import Image
from app.main import app

client=TestClient(app)
HEAD={"X-API-Key":os.environ["APP_API_KEY"]}

def picture(color=(10,70,180)):
    out=io.BytesIO();Image.new("RGB",(90,90),color).save(out,format="PNG");return out.getvalue()

def add(data=None,name="test.png",headers=HEAD):
    return client.post("/api/analyze",headers=headers,files={"file":(name,data or picture(),"image/png")})

def test_requires_auth():
    assert add(headers={}).status_code==401
    assert client.get("/api/investigations").status_code==401

def test_invalid_image():
    assert add(b"not image").status_code==415
    assert client.post("/api/analyze",headers=HEAD,files={"file":("bad.txt",b"aaa","text/plain")}).status_code==415

def test_empty_list_and_exif_absent():
    assert client.get("/api/investigations",headers=HEAD).status_code==200
    r=add();assert r.status_code==200
    assert r.json()["metadata"]["gps_present"] is False
    assert r.json()["metadata"]["width"]==90

def test_exact_duplicate_and_delete():
    first=add().json()
    second=add().json()
    assert any(m["id"]==first["id"] and m["type"]=="exact" for m in second["matches"])
    assert client.get(f"/api/investigations/{first['id']}/report.pdf",headers=HEAD).content.startswith(b"%PDF")
    assert client.get(f"/api/investigations/{first['id']}/report.json",headers=HEAD).status_code==200
    assert client.delete(f"/api/investigations/{first['id']}",headers=HEAD).json()["deleted"]
    assert client.get(f"/api/investigations/{first['id']}",headers=HEAD).status_code==404

def test_compare():
    data=picture()
    r=client.post("/api/compare",headers=HEAD,files={"first":("a.png",data,"image/png"),"second":("b.png",data,"image/png")})
    assert r.status_code==200 and r.json()["exact"] is True and r.json()["phash_distance"]==0

def test_external_results_not_invented():
    r=add().json()
    assert r["external_results"]==[] and r["external_status"]=="not_configured"
    assert client.post("/api/analyze-url",headers=HEAD).status_code==501

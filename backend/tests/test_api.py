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
    assert r["external_results"]==[] and r["external_status"]=="not_checked"
    assert client.post("/api/analyze-url",headers=HEAD).status_code==501

def test_public_search_failed_provider_not_fake(monkeypatch):
    import httpx
    from app import main
    class ErrorClient:
        def __init__(self,*args,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def get(self,*args,**kwargs): raise httpx.ConnectError("unavailable")
    monkeypatch.setattr(main.httpx,"AsyncClient",ErrorClient)
    item=add().json()
    result=client.post(f"/api/investigations/{item['id']}/search/commons",headers=HEAD)
    assert result.status_code==200
    assert result.json()["external_status"]=="provider_unavailable"
    assert result.json()["external_results"]==[]

def test_public_search_verified_response(monkeypatch):
    from app import main
    class Response:
        def raise_for_status(self): pass
        def json(self):
            return {"query":{"allimages":[{"title":"File:Example.png",
            "url":"https://upload.wikimedia.org/wikipedia/commons/1/11/Example.png",
            "descriptionurl":"https://commons.wikimedia.org/wiki/File:Example.png",
            "timestamp":"2020-01-01T00:00:00Z"}]}}
    class Client:
        def __init__(self,*args,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def get(self,url,params):
            assert params["aisha1"]
            assert url=="https://commons.wikimedia.org/w/api.php"
            return Response()
    monkeypatch.setattr(main.httpx,"AsyncClient",Client)
    item=add().json()
    result=client.post(f"/api/investigations/{item['id']}/search/commons",headers=HEAD)
    assert result.status_code==200
    assert result.json()["external_status"]=="checked"
    assert len(result.json()["external_results"])==1
    detail=client.get(f"/api/investigations/{item['id']}",headers=HEAD).json()
    assert len(detail["external_results"])==1
    client.delete(f"/api/investigations/{item['id']}",headers=HEAD)

def test_crop_compare_scene_features():
    import numpy as np
    rng=np.random.default_rng(42)
    pixels=rng.integers(0,256,size=(500,500),dtype=np.uint8)
    original=Image.fromarray(pixels).convert("RGB")
    cropped=original.crop((90,70,430,410))
    aa=io.BytesIO();bb=io.BytesIO()
    original.save(aa,format="PNG");cropped.save(bb,format="PNG")
    r=client.post("/api/compare",headers=HEAD,files={"first":("a.png",aa.getvalue(),"image/png"),
                                                       "second":("b.png",bb.getvalue(),"image/png")})
    assert r.status_code==200
    result=r.json()
    assert result["exact"] is False
    assert result["possibly_same_scene"] is True
    assert result["feature_inliers"]>=10

def test_reverse_requires_auth_and_empty_results():
    item=add().json()
    path=f"/api/investigations/{item['id']}/reverse"
    assert client.get(path).status_code == 401
    response=client.get(path,headers=HEAD)
    assert response.status_code == 200
    result=response.json()
    assert result["scope"] == "private_upload_index_only"
    assert result["no_public_identity_search"] is True
    assert result["searched_records"] >= 0
    assert result["external"]["external_results"] == []

def test_reverse_exact_duplicate():
    a=add().json()
    b=add().json()
    result=client.get(f"/api/investigations/{b['id']}/reverse",headers=HEAD).json()
    assert any(m["id"] == a["id"] and m["verified_exact"]
               and m["match_type"] == "exact_bytes" for m in result["matches"])
    assert all(m["source_url"] is None for m in result["matches"])

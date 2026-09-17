import os
import json
import shutil
import base64
from urllib.parse import unquote
from datetime import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests

app = FastAPI(title="기술정책부 통합 대시보드 API")

# 프론트엔드 CORS 통신 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_FILE = "config_preset.json"
DATA_FILE = "department_records.json"
WORK_TABS = ["leader", "admin", "rf", "radio", "research", "procurement", "maintenance", "etc"]

def init_files():
    if not os.path.exists(CONFIG_FILE):
        default_cfg = {
            "preset_name": "기본 프리셋",
            "nas_path": "",
            "attachment_path": "C:/git-work/system_maintenance_history/uploads",
            "local_backup_path": "./local_exports",
            "kakao_token": "",
            "kakao_refresh_token": "", # 추가됨: 리프레시 토큰
            "kakao_client_id": ""      # 추가됨: 카카오 REST API 키
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default_cfg, f, ensure_ascii=False, indent=2)

    if not os.path.exists(DATA_FILE):
        init_data = {tab: [] for tab in WORK_TABS}
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(init_data, f, ensure_ascii=False, indent=2)

init_files()

class ConfigModel(BaseModel):
    preset_name: str = "기본 프리셋"
    nas_path: str
    attachment_path: str = "C:/git-work/system_maintenance_history/uploads"
    local_backup_path: str = "./local_exports"
    kakao_token: str
    kakao_refresh_token: str = "" # 추가됨
    kakao_client_id: str = ""     # 추가됨

class RecordPayload(BaseModel):
    tab: str
    data: dict

class MultiTabImportItem(BaseModel):
    tab: str
    data: dict

class MultiTabImportPayload(BaseModel):
    items: list[MultiTabImportItem]

class ExportSyncRequest(BaseModel):
    tab_name: str
    file_type: str
    file_name: str
    file_content_base64: str

# 서버 헬스체크
@app.get("/api/health")
def health_check():
    return {"status": "online", "timestamp": datetime.now().isoformat()}

@app.get("/api/config")
def get_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

@app.post("/api/config")
def save_config(cfg: ConfigModel):
    # 기존 파일 내용을 먼저 읽어서 토큰 정보가 덮어씌워지는 것을 방지
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        existing_cfg = json.load(f)
        
    data = cfg.dict()
    if data.get("attachment_path"):
        data["attachment_path"] = os.path.normpath(data["attachment_path"].strip())
    if data.get("nas_path"):
        data["nas_path"] = os.path.normpath(data["nas_path"].strip())
    
    # 프론트엔드에서 빈 값으로 전송되더라도 기존 리프레시 토큰과 클라이언트 ID 유지
    if not data.get("kakao_refresh_token"):
        data["kakao_refresh_token"] = existing_cfg.get("kakao_refresh_token", "")
    if not data.get("kakao_client_id"):
        data["kakao_client_id"] = existing_cfg.get("kakao_client_id", "")
        
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        
    print(f"[*] 설정 저장 완료 - 첨부문서 저장소: {data.get('attachment_path')}")
    return {"status": "success", "message": "설정이 성공적으로 저장되었습니다."}

@app.get("/api/records")
def get_records():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

@app.post("/api/records")
def save_or_update_record(payload: RecordPayload):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        all_data = json.load(f)

    tab = payload.tab
    if tab not in all_data:
        all_data[tab] = []

    item = payload.data
    if item.get("id"):
        updated = False
        for idx, existing in enumerate(all_data[tab]):
            if existing.get("id") == item["id"]:
                all_data[tab][idx] = item
                updated = True
                break
        if not updated:
            all_data[tab].insert(0, item)
    else:
        item["id"] = datetime.now().strftime("%Y%m%d%H%M%S%f")
        all_data[tab].insert(0, item)

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    return {"status": "success", "item": item}

@app.post("/api/records/multi-import")
def multi_tab_import(payload: MultiTabImportPayload):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        all_data = json.load(f)

    count = 0
    for it in payload.items:
        tab = it.tab
        data = it.data
        if tab not in all_data:
            all_data[tab] = []
        if not data.get("id"):
            data["id"] = datetime.now().strftime("%Y%m%d%H%M%S%f") + str(count)
        all_data[tab].insert(0, data)
        count += 1

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(all_data, f, ensure_ascii=False, indent=2)

    return {"status": "success", "imported_count": count}

@app.delete("/api/records")
def delete_record(tab: str, id: str):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        all_data = json.load(f)

    if tab in all_data:
        all_data[tab] = [r for r in all_data[tab] if r.get("id") != id]
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
        return {"status": "success", "message": "삭제 완료"}
    raise HTTPException(status_code=404, detail="해당 탭을 찾을 수 없습니다.")

@app.post("/api/upload-attachment")
async def upload_attachment(file: UploadFile = File(...)):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    raw_path = cfg.get("attachment_path", "./uploaded_attachments")
    target_dir = os.path.normpath(raw_path.strip() if raw_path else "./uploaded_attachments")
    os.makedirs(target_dir, exist_ok=True)

    file_path = os.path.join(target_dir, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"[+] 첨부파일 디스크 저장 완료 -> {file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"저장 실패: {str(e)}")

    return {"status": "success", "filename": file.filename, "saved_path": file_path}

@app.get("/api/attachments/{filename}")
def download_or_view_attachment(filename: str):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    decoded_filename = unquote(filename)
    raw_path = cfg.get("attachment_path", "./uploaded_attachments")
    target_dir = os.path.normpath(raw_path.strip() if raw_path else "./uploaded_attachments")
    file_path = os.path.join(target_dir, decoded_filename)

    if os.path.exists(file_path):
        return FileResponse(file_path, filename=decoded_filename)
    
    raise HTTPException(status_code=404, detail=f"지정된 폴더에 파일이 없습니다: {decoded_filename}")

@app.delete("/api/attachments/{filename}")
def delete_attachment_file(filename: str):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    decoded_filename = unquote(filename)
    raw_path = cfg.get("attachment_path", "./uploaded_attachments")
    target_dir = os.path.normpath(raw_path.strip() if raw_path else "./uploaded_attachments")
    file_path = os.path.join(target_dir, decoded_filename)

    if os.path.exists(file_path):
        try:
            os.remove(file_path)
            return {"status": "success", "message": "삭제 완료"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"삭제 실패: {str(e)}")
    return {"status": "success", "message": "이미 존재하지 않는 파일입니다."}

# [추가된 함수] 카카오 토큰 리프레시 로직
def refresh_kakao_token(client_id: str, refresh_token: str):
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token
    }
    res = requests.post(url, data=data)
    if res.status_code == 200:
        return res.json()
    else:
        print(f"[!] 카카오 토큰 갱신 실패: {res.text}")
        return None

@app.post("/api/export-sync")
def handle_export_sync(req: ExportSyncRequest):
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # 1. 로컬(PC) 저장 경로를 절대 경로로 명확히 변환
    local_dir = os.path.abspath(cfg.get("local_backup_path", "./local_exports").strip())
    os.makedirs(local_dir, exist_ok=True)
    local_filepath = os.path.join(local_dir, req.file_name)
    file_bytes = base64.b64decode(req.file_content_base64)
    with open(local_filepath, "wb") as f:
        f.write(file_bytes)

    nas_status = "미지정"
    nas_path = cfg.get("nas_path", "").strip()
    
    if nas_path:
        try:
            # [수정된 부분 1] Z: 처럼 드라이브 문자만 적었을 경우 슬래시(\)를 강제 추가
            if len(nas_path) == 2 and nas_path.endswith(':'):
                nas_path += '\\'
                
            # [수정된 부분 2] 운영체제가 인식하는 완벽한 절대 경로로 변환
            normalized_nas = os.path.abspath(nas_path)
            
            if not os.path.exists(normalized_nas):
                os.makedirs(normalized_nas, exist_ok=True)
                
            target_nas_file = os.path.join(normalized_nas, req.file_name)
            
            # 파일 복사 실행
            shutil.copyfile(local_filepath, target_nas_file)
            
            # [추가된 부분 3] 실제로 파일이 써졌는지 크기를 확인하여 검증
            copied_size = os.path.getsize(target_nas_file)
            
            nas_status = f"성공 ({target_nas_file})"
            
            # 터미널에 정확한 저장 위치와 크기 출력
            print(f"\n[+] 로컬 백업 완료: {local_filepath} ({os.path.getsize(local_filepath)} bytes)")
            print(f"[+] NAS 동기화 완료: {target_nas_file} ({copied_size} bytes)")
            
        except PermissionError:
            nas_status = "실패 (접근 권한 없음)"
            print(f"[!] NAS 에러: '{normalized_nas}' 에 파일을 쓸 권한이 없습니다.")
        except FileNotFoundError:
            nas_status = "실패 (경로 찾을 수 없음)"
            print(f"[!] NAS 에러: '{normalized_nas}' 경로에 연결할 수 없습니다.")
        except Exception as e:
            nas_status = f"실패 ({str(e)})"
            print(f"[!] NAS 알 수 없는 에러: {str(e)}")

    kakao_status = "미설정"
    kakao_token = cfg.get("kakao_token", "").strip()
    kakao_refresh_token = cfg.get("kakao_refresh_token", "").strip()
    kakao_client_id = cfg.get("kakao_client_id", "").strip()

    if kakao_token:
        url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        
        def send_kakao_msg(access_token):
            headers = {"Authorization": f"Bearer {access_token}"}
            message_text = (
                f"[기술정책부 대시보드 리포트 생성]\n"
                f"• 구분: {req.tab_name}\n"
                f"• 파일명: {req.file_name}\n"
                f"• 출력 일시: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"• NAS 동기화: {nas_status}"
            )
            payload = {
                "template_object": json.dumps({
                    "object_type": "text",
                    "text": message_text,
                    "link": {"web_url": "http://localhost:8000"}
                })
            }
            return requests.post(url, headers=headers, data=payload)

        res = send_kakao_msg(kakao_token)
        
        if res.status_code == 401 and kakao_refresh_token and kakao_client_id:
            print("[*] 카카오 토큰 만료 감지. 재발급을 시도합니다...")
            new_tokens = refresh_kakao_token(kakao_client_id, kakao_refresh_token) # 상단에 작성했던 갱신 함수 호출
            
            if new_tokens:
                cfg["kakao_token"] = new_tokens.get("access_token")
                if "refresh_token" in new_tokens:
                    cfg["kakao_refresh_token"] = new_tokens.get("refresh_token")
                
                with open(CONFIG_FILE, "w", encoding="utf-8") as config_file:
                    json.dump(cfg, f=config_file, ensure_ascii=False, indent=2)
                
                res = send_kakao_msg(cfg["kakao_token"])
                kakao_status = "전송 완료 (토큰 자동 갱신됨)" if res.status_code == 200 else f"실패 ({res.text})"
            else:
                kakao_status = "토큰 갱신 실패 (다시 수동 발급 필요)"
        else:
            kakao_status = "전송 완료" if res.status_code == 200 else f"실패 ({res.text})"

    return {
        "status": "success",
        "nas_result": nas_status,
        "kakao_result": kakao_status,
        "local_saved": local_filepath
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
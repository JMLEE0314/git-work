import requests

# ================= 매개변수 설정 (본인의 정보로 변경하세요) =================
REST_API_KEY = "86644265a2e44f2bdbcd84b61111156f"
REDIRECT_URI = "https://localhost"  # 1단계에서 설정한 Redirect URI
AUTHORIZATION_CODE = "qdW8l1ElGgs3lgVP-W1hIHFMSzXSHlYt4Jg5doyX2iUzPBeTV1NDbAAAAAQKDSKZAAABoK1W4sMFVMIyByjmyg"

def get_kakao_access_token(api_key, redirect_uri, code):
    """
    인가 코드(Authorization Code)를 사용하여 액세스 토큰을 발급받는 함수
    """
    url = "https://kauth.kakao.com/oauth/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": api_key,
        "redirect_uri": redirect_uri,
        "code": code
    }
    
    response = requests.post(url, data=data)
    result = response.json()
    
    if response.status_code == 200:
        print("[+] 토큰 발급 성공!")
        print(f"Access Token: {result.get('access_token')}")
        print(f"Refresh Token: {result.get('refresh_token')}")
        return result.get('access_token')
    else:
        print(f"[!] 토큰 발급 실패: {result}")
        return None

def send_test_message(access_token):
    """
    발급받은 액세스 토큰으로 나에게 테스트 카카오톡 메시지를 보내는 함수
    """
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }
    payload = {
        "template_object": '{"object_type": "text", "text": "기술정책부 카카오톡 연동 테스트 성공!", "link": {"web_url": "http://localhost:8000"}}'
    }
    
    res = requests.post(url, headers=headers, data=payload)
    if res.status_code == 200:
        print("[+] 카카오톡 메시지 전송 성공! 카카오톡 앱을 확인해 보세요.")
    else:
        print(f"[!] 메시지 전송 실패: {res.text}")

# --- 실행 부분 ---
if __name__ == "__main__":
    token = get_kakao_access_token(REST_API_KEY, REDIRECT_URI, AUTHORIZATION_CODE)
    if token:
        send_test_message(token)
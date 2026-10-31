import os

# 테스트가 실제 키와 운영 설정을 읽지 않게 합니다.
os.environ["GUARD_ENV_FILE"] = ""

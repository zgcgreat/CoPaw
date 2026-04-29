# -*- coding: utf-8 -*-
# 空函数，使用行内文件替换
import json
import time
from typing import Any


def encrypt_string(db_passwd: str) -> str:
    return db_passwd


def decrypt_string(db_passwd: str) -> str:
    return db_passwd


def encrypt_sm2_sign_string(sign: str) -> str:
    return sign


# 基于userInfo获取auth_token，authtoken过期时间2h
def get_auth_token(userInfo: Any) -> str:
    if isinstance(userInfo, str):
        return userInfo
    return json.dumps(userInfo, ensure_ascii=False)


# exp为userInfo过期时间，默认7天，可续期
def get_user_info(access_token: str) -> dict:
    return {
        "userInfo": access_token,
        "exp": int(time.time()) + 7 * 24 * 60 * 60,
    }


# 扩展userInfo过期时间
def extend_user_info_expire(userInfo: str) -> str:
    return userInfo

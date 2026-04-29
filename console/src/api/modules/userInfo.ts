/**
 * 调用后端 /user-info/query 接口查询用户详细信息
 */

import { request } from "../request";
import { BBK_ID_MAP } from "../../constants/bbk";

/** 用户信息查询请求参数 */
export interface UserInfoQueryRequest {
  /** 用户 ID */
  keyWord: string;
  /** 比较类型，默认 EQ */
  compareType?: string;
}

/** 用户信息查询响应 */
export interface UserInfoQueryResponse {
  /** 响应数据 */
  data: {
    code: string;
    message: string;
    result: boolean;
    data: Array<{
      userName: string;
      pathName: string;
    }>;
  };
}

/** 用户信息提取结果 */
export interface UserInfoExtractResult {
  userName: string | null;
  bbk: string | null;
}

/**
 * 查询用户信息 API
 *
 * @param userId - 用户 ID
 * @returns 用户信息数据
 */
export async function fetchUserInfo(
  userId: string,
): Promise<UserInfoQueryResponse["data"] | null> {
  try {
    const result = await request<UserInfoQueryResponse>("/user-info/query", {
      method: "POST",
      body: JSON.stringify({
        keyWord: userId,
        compareType: "EQ",
      }),
    });
    return result.data;
  } catch (error) {
    console.error("[UserInfo] API request error:", error);
    return null;
  }
}

/**
 * 从 pathName 中提取第一个"/"和第二个"/"之间的内容
 *
 * @param pathName - 路径名称，如 "某企业/总行/生产部/某组"
 * @returns 提取的内容，如 "总行"
 */
function extractBbkNameFromPathName(pathName: string): string | null {
  const parts = pathName.split("/");
  // parts[0] = "某企业", parts[1] = "总行", parts[2] = "生产部"
  if (parts.length >= 2 && parts[1]) {
    return parts[1];
  }
  return null;
}

/**
 * 根据 bbk 名称查找 BBK_ID_MAP 中的 value
 *
 * @param bbkName - bbk 名称，如 "总行"
 * @returns 对应的 value，如 "100"
 */
function findBbkValue(bbkName: string): string | null {
  const item = BBK_ID_MAP.find((item) => item.label === bbkName);
  return item?.value ?? null;
}

/**
 * 从用户信息数据中提取用户名称和 bbk
 *
 * @param data - 用户信息数据
 * @returns 用户名称和 bbk
 */
export function extractUserInfo(
  data: UserInfoQueryResponse["data"] | null,
): UserInfoExtractResult {
  const result: UserInfoExtractResult = {
    userName: null,
    bbk: null,
  };

  if (!data || !data.data || data.data.length === 0) {
    return result;
  }

  const userInfo = data.data[0];

  // 提取 userName
  if (userInfo.userName) {
    result.userName = userInfo.userName;
  }

  // 提取 pathName 并映射 bbk
  if (userInfo.pathName) {
    const bbkName = extractBbkNameFromPathName(userInfo.pathName);
    if (bbkName) {
      result.bbk = findBbkValue(bbkName);
    }
  }

  return result;
}
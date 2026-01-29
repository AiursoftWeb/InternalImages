use axum::{
    extract::Request,
    http::{StatusCode, HeaderMap},
    middleware::Next,
    response::Response,
};
use std::sync::OnceLock;

// 存储 Key 的全局静态变量
static API_KEY: OnceLock<String> = OnceLock::new();

/// 供 main 函数调用，用于初始化 Key
/// 如果已经被设置过，返回错误
pub fn set_api_key(key: String) -> Result<(), String> {
    API_KEY.set(key).map_err(|_| "API_KEY already set".to_string())
}

/// 中间件逻辑
pub async fn auth_middleware(
    headers: HeaderMap,
    request: Request,
    next: Next,
) -> Result<Response, StatusCode> {
    // 安全获取 Key
    // 如果 main 没初始化它，这里不应该 panic，而是返回 500 系统错误
    let system_key = match API_KEY.get() {
        Some(k) => k,
        None => {
            tracing::error!("CRITICAL: API_KEY not initialized!"); 
            return Err(StatusCode::INTERNAL_SERVER_ERROR);
        }
    };

    let user_key = headers
        .get("x-api-key")
        .and_then(|value| value.to_str().ok());

    match user_key {
        Some(key) if key == system_key => Ok(next.run(request).await),
        _ => Err(StatusCode::UNAUTHORIZED),
    }
}
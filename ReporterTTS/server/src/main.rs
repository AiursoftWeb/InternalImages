mod auth; 
use axum::{
    extract::DefaultBodyLimit,
    routing::{get, post},
    Router,
    middleware
};
pub use bytes::Bytes;
use candle_core::{DType, Device};
use clap::Parser;
pub use futures_util::Stream;
use server::handlers::{
    encode_speech::encode_speaker, speech::generate_speech, supported_voices::get_supported_voices,
};
use server::state::AppState;
use server::utils::load::{load_codec, load_lm, Args};
use std::sync::Arc;
use std::time::Instant;
use std::env;
use std::process;
// Re-export the key types
use tower_http::cors::{Any, CorsLayer};

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    
        dotenvy::dotenv().ok();
    // 2. [关键步骤] 启动时校验配置 (Fail Fast)
    // 尝试读取环境变量，如果读不到，打印错误并终止进程
    let api_key = match env::var("API_KEY") {
        Ok(k) if !k.is_empty() => k,
        _ => {
            eprintln!("❌ 错误: 环境变量 API_KEY 未设置或为空。");
            eprintln!("   请在 .env 文件中设置 API_KEY=... 或通过 export 设置。");
            process::exit(1); // 非零退出码，告诉运维/Docker 启动失败了
        }
    };

    // 3. 将 Key 注入到 auth 模块的全局状态中
    if let Err(e) = auth::set_api_key(api_key) {
        eprintln!("❌ 初始化失败: {}", e);
        process::exit(1);
    }



    let args = Args::parse();

    #[cfg(feature = "cuda")]
    let device = Device::cuda_if_available(0)?;

    #[cfg(feature = "metal")]
    let device = Device::new_metal(0)?;

    #[cfg(not(any(feature = "cuda", feature = "metal")))]
    let device = Device::Cpu;

    let checkpoint_dir = if let Some(raw_dir) = args.checkpoint.as_ref() {
        Some(raw_dir.canonicalize().unwrap())
    } else {
        None
    };
    // TODO: Figure out why BF16 is breaking on Metal
    #[cfg(feature = "cuda")]
    let dtype = DType::BF16;
    #[cfg(not(feature = "cuda"))]
    let dtype = DType::F32;

    println!("Loading {:?} model on {:?}", args.fish_version, device);
    let start_load = Instant::now();
    let lm_state = load_lm(&args, checkpoint_dir, dtype, &device)?;
    let (codec_state, sample_rate) =
        load_codec(&args, dtype, &device, lm_state.config.num_codebooks)?;
    let dt = start_load.elapsed();
    println!("Models loaded in {:.2}s", dt.as_secs_f64());

    let state = Arc::new(AppState {
        lm: Arc::new(lm_state),
        codec: Arc::new(codec_state),
        device,
        model_type: args.fish_version,
        sample_rate,
    });

    // Create router
    let app = Router::new()
        .route("/v1/audio/speech", post(generate_speech))
        .route("/v1/audio/encoding", post(encode_speaker))
        .route("/v1/voices", get(get_supported_voices))
        // .route_layer(middleware::from_fn(auth::auth_middleware))
        .layer(DefaultBodyLimit::max(32 * 1024 * 1024))
        .layer(
            CorsLayer::new()
                .allow_origin(Any)
                .allow_methods(Any)
                .allow_headers(Any),
        )
        .with_state(state);

    // Run server
    let addr = format!("0.0.0.0:{}", args.port);
    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).tcp_nodelay(true).await?;

    Ok(())
}

// ============================================================
// config.js —— 纯客户端配置：多厂商支持 + key 管理
// key 只存在用户手机本地（localStorage），永不上传、不走任何服务器
// ============================================================

// 预设厂商表：新增厂商只需在这里加一行
// base_url 统一用 OpenAI 兼容的 /v1 地址
// 注意：models 只是"参考建议"，界面支持直接输入任意模型名（不受此列表限制）
const PROVIDERS = {
  deepseek: {
    name: "DeepSeek",
    base_url: "https://api.deepseek.com/v1",
    models: ["deepseek-chat", "deepseek-reasoner"],
  },
  moonshot: {
    name: "Kimi（月之暗面）",
    base_url: "https://api.moonshot.cn/v1",
    models: ["kimi-k2-0711-preview", "moonshot-v1-128k", "moonshot-v1-32k"],
  },
  dashscope: {
    name: "通义千问（阿里云）",
    base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    models: ["qwen3-max", "qwen3-plus", "qwen3-turbo", "qwen-max"],
  },
  zhipu: {
    name: "智谱 GLM",
    base_url: "https://open.bigmodel.cn/api/paas/v4",
    models: ["glm-4.5", "glm-4.5-air", "glm-4-plus", "glm-4-flash"],
  },
  ollama: {
    name: "Ollama（本地）",
    base_url: "http://localhost:11434/v1",
    models: ["qwen3", "llama3.2", "deepseek-r1", "deepseek-v3"],
  },
  custom: {
    name: "自定义（OpenAI 兼容）",
    base_url: "",
    models: [],
  },
};

// ── 配置读写（localStorage）──────────────────────────
const KEY_PROVIDER = "rental_provider";
const KEY_KEY = "rental_api_key";
const KEY_MODEL = "rental_model";
const KEY_CUSTOM_BASE = "rental_custom_base";
const KEY_CUSTOM_MODEL = "rental_custom_model";

function getProviderId() {
  return localStorage.getItem(KEY_PROVIDER) || "deepseek";
}
function getProvider() {
  return PROVIDERS[getProviderId()] || PROVIDERS.deepseek;
}

function getApiKey() {
  const k = localStorage.getItem(KEY_KEY);
  return k ? k.trim() : null;
}

// 当前生效的 base_url：自定义厂商用用户填的，否则用预设
function getBaseUrl() {
  const id = getProviderId();
  if (id === "custom") {
    return (localStorage.getItem(KEY_CUSTOM_BASE) || "").trim();
  }
  return getProvider().base_url;
}

// 当前生效的模型名：自定义厂商用用户填的，否则用预设里选的
function getModel() {
  const id = getProviderId();
  if (id === "custom") {
    return (localStorage.getItem(KEY_CUSTOM_MODEL) || "").trim();
  }
  return localStorage.getItem(KEY_MODEL) || getProvider().models[0];
}

function saveConfig(providerId, apiKey, model, customBase, customModel) {
  localStorage.setItem(KEY_PROVIDER, providerId);
  localStorage.setItem(KEY_KEY, (apiKey || "").trim());
  localStorage.setItem(KEY_MODEL, model || "");
  localStorage.setItem(KEY_CUSTOM_BASE, (customBase || "").trim());
  localStorage.setItem(KEY_CUSTOM_MODEL, (customModel || "").trim());
}

function hasApiKey() {
  return !!getApiKey();
}

function clearApiKey() {
  localStorage.removeItem(KEY_KEY);
}

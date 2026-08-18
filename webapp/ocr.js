// ============================================================
// ocr.js —— 图片文字识别（Tesseract.js 纯离线 OCR）
// 功能：用户选图/拍照 → 识别文字 → 填入 textarea
//
// ★ 下载加速：
//   1. 语言包走 jsdelivr CDN（实测 19.2MB 约 23 秒，官方源要 6 分多钟，快了约 18 倍）
//   2. 页面加载后自动后台预下载（preloadOcr），用户点识别时几乎不用等
//   3. worker 复用：只创建一次，后续识别不再重新下载
// ============================================================

// 语言包 CDN 源（jsdelivr 国内节点快；npm 包版本 1.0.0，traineddata 版本 4.0.0）
const OCR_LANG_PATH = "https://cdn.jsdelivr.net/npm/@tesseract.js-data/chi_sim@1.0.0/4.0.0";

let _ocrWorker = null;
let _ocrLoading = null;    // 进行中的加载 Promise，防止并发重复创建
let _ocrOnProgress = null; // 识别进度回调（创建 worker 时绑定，识别时更新）

// 创建 OCR worker（懒加载 + 复用；预加载和正式识别共用）
function createOcrWorker() {
  if (_ocrWorker) return Promise.resolve(_ocrWorker);
  if (_ocrLoading) return _ocrLoading;
  _ocrLoading = Tesseract.createWorker(["chi_sim", "eng"], 1, {
    langPath: OCR_LANG_PATH,
    logger: (m) => {
      // 把所有阶段的进度都上报（下载语言包 / 初始化 / 识别文字）
      if (_ocrOnProgress) {
        _ocrOnProgress({
          status: m.status,
          progress: (m.progress != null && m.progress >= 0) ? Math.round(m.progress * 100) : -1,
        });
      }
    },
  }).then(w => { _ocrWorker = w; _ocrLoading = null; return w; })
    .catch(e => { _ocrLoading = null; throw e; });
  return _ocrLoading;
}

// 预下载：后台静默初始化 worker 并下载语言包
// 失败就静默忽略——不影响其它功能，用户真正用 OCR 时会再尝试并看到进度
function preloadOcr() {
  createOcrWorker().catch(() => {});
}

// 从图片识别文字
// imageInput: File 或 Blob（来自 <input type="file">）
// onProgress: ({status, progress}) => void   progress 为 0-100 的百分比，-1 表示该阶段无进度值
// 返回识别到的文本
async function recognizeImage(imageInput, onProgress) {
  _ocrOnProgress = onProgress || null;
  const worker = await createOcrWorker();
  const { data } = await worker.recognize(imageInput);
  return data.text.trim();
}

// 将文件转为可预览的 URL
function fileToURL(file) {
  return URL.createObjectURL(file);
}

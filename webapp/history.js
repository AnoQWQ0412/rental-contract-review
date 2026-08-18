// ============================================================
// history.js —— 审查记录管理（纯本地 localStorage，最多保留 30 条）
// 功能：保存 / 列表 / 查看 / 删除 / 清空
// ============================================================

const HISTORY_KEY = "rental_history";
const MAX_RECORDS = 30;

// 保存一条审查记录
function saveHistory(contractText, result) {
  const records = loadHistory();
  const record = {
    id: Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
    time: new Date().toISOString(),
    preview: contractText.slice(0, 60).replace(/\n/g, " "),
    contract: contractText,
    result: result,
  };
  records.unshift(record); // 最新在最前
  while (records.length > MAX_RECORDS) {
    records.pop(); // 超出上限，删除最旧的
  }
  localStorage.setItem(HISTORY_KEY, JSON.stringify(records));
}

// 加载所有记录
function loadHistory() {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch (e) {
    return [];
  }
}

// 删除单条记录
function deleteHistory(id) {
  const records = loadHistory().filter(r => r.id !== id);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(records));
}

// 清空所有记录
function clearHistory() {
  localStorage.removeItem(HISTORY_KEY);
}

// 格式化时间
function formatTime(iso) {
  const d = new Date(iso);
  const pad = n => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

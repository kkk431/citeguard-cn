/* G5: turn transport/status failures into a next step the user can act on. */
(function () {
  var MAP = {
    400: "请求内容不完整，请检查输入后重试",
    401: "没有权限，请检查访问令牌或登录状态",
    403: "没有权限访问这项内容",
    404: "没有找到对应内容，请返回上一步",
    409: "状态已经变化，请刷新页面后重试",
    413: "文件太大，请压缩或拆分后再试",
    422: "内容格式不符合要求，请检查后重试",
    429: "请求太频繁，请稍后重试",
    500: "服务内部错误，请稍后重试",
    502: "上游服务暂不可用，请稍后重试",
    503: "服务暂不可用，请稍后重试",
    504: "服务响应超时，请稍后重试"
  };
  window.humanHttpError = function (status, detail, fallback) {
    if (detail && typeof detail === "object") {
      detail = detail.message || detail.error || detail.detail || "";
      if (detail && typeof detail === "object") detail = detail.message || "";
    }
    var text = String(detail == null ? "" : detail)
      .replace(/HTTP\s*\d{3}/gi, "")
      .replace(/\s+/g, " ")
      .trim();
    if (text) return text;
    return MAP[status] || fallback || "请求没有完成，请稍后重试";
  };
})();

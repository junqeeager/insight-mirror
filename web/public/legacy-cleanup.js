/**
 * 清理旧前端残留：注销本来源所有 Service Worker 并清空 CacheStorage。
 * 旧 Streamlit/旧 React 部署可能注册过 SW 或缓存过旧 bundle，
 * 新页面每次加载都执行一次（幂等、静默），避免旧脚本继续接管页面。
 */
(function () {
  try {
    if ("serviceWorker" in navigator) {
      navigator.serviceWorker
        .getRegistrations()
        .then(function (registrations) {
          registrations.forEach(function (registration) {
            registration.unregister();
          });
        })
        .catch(function () {});
    }
  } catch (e) {
    /* 忽略：无 SW 或受限环境下不阻塞页面 */
  }

  try {
    if ("caches" in window) {
      caches
        .keys()
        .then(function (keys) {
          keys.forEach(function (key) {
            caches.delete(key);
          });
        })
        .catch(function () {});
    }
  } catch (e) {
    /* 忽略：无 Cache API 或受限环境下不阻塞页面 */
  }
})();

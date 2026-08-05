import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/AuthContext";

export function usePreviewData<T>(
  fetcher: () => Promise<T>,
  mock: T,
  deps: unknown[] = [],
) {
  const { isAuthenticated } = useAuth();
  const [data, setData] = useState<T>(mock);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((n) => n + 1), []);

  useEffect(() => {
    if (!isAuthenticated) {
      setData(mock);
      setLoading(false);
      setError(null);
      return;
    }

    let active = true;
    setLoading(true);
    setError(null);
    fetcher()
      .then((result) => {
        if (!active) return;
        setData(result);
        setLoading(false);
      })
      .catch((err) => {
        if (!active) return;
        setLoading(false);
        if (err?.response?.status !== 401) {
          setError(err?.response?.data?.detail ?? "数据加载失败，请稍后重试");
        }
      });
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, tick, ...deps]);

  return { data, loading, error, refresh };
}

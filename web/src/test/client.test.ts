import { afterEach, describe, expect, it, vi } from "vitest";
import {
  api,
  consumeUnauthorizedFlag,
  setUnauthorizedHandler,
} from "../api/client";

describe("API 401 拦截", () => {
  afterEach(() => {
    setUnauthorizedHandler(null);
    api.defaults.adapter = undefined;
  });

  it("接口返回 401 时触发登录引导回调", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    api.defaults.adapter = (async () => {
      const error = new Error("unauthorized") as Error & {
        response: { status: number };
      };
      error.response = { status: 401 };
      throw error;
    }) as never;

    await expect(api.get("/stats")).rejects.toBeTruthy();
    expect(handler).toHaveBeenCalledTimes(1);
    expect(consumeUnauthorizedFlag()).toBe(true);
  });

  it("非 401 错误不触发登录引导", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    api.defaults.adapter = (async () => {
      const error = new Error("server") as Error & {
        response: { status: number };
      };
      error.response = { status: 500 };
      throw error;
    }) as never;

    await expect(api.get("/stats")).rejects.toBeTruthy();
    expect(handler).not.toHaveBeenCalled();
    expect(consumeUnauthorizedFlag()).toBe(false);
  });
});

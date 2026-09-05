import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  /** 清理上一用例挂载的组件和本地持久化状态。 */
  cleanup();
  localStorage.clear();
});

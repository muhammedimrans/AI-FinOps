import { beforeEach, describe, expect, it } from "vitest";
import { useNotificationStore } from "../stores/notifications";

describe("useNotificationStore", () => {
  beforeEach(() => {
    useNotificationStore.setState({ readIds: {}, dismissedIds: {} });
  });

  it("markRead flags a single alert as read", () => {
    useNotificationStore.getState().markRead("a1");
    expect(useNotificationStore.getState().readIds["a1"]).toBe(true);
    expect(useNotificationStore.getState().readIds["a2"]).toBeUndefined();
  });

  it("markAllRead flags every given id as read", () => {
    useNotificationStore.getState().markAllRead(["a1", "a2", "a3"]);
    const { readIds } = useNotificationStore.getState();
    expect(readIds["a1"]).toBe(true);
    expect(readIds["a2"]).toBe(true);
    expect(readIds["a3"]).toBe(true);
  });

  it("dismiss hides a single alert independently of read state", () => {
    useNotificationStore.getState().dismiss("a1");
    expect(useNotificationStore.getState().dismissedIds["a1"]).toBe(true);
    expect(useNotificationStore.getState().readIds["a1"]).toBeUndefined();
  });

  it("clearAll dismisses every given id at once", () => {
    useNotificationStore.getState().clearAll(["a1", "a2"]);
    const { dismissedIds } = useNotificationStore.getState();
    expect(dismissedIds["a1"]).toBe(true);
    expect(dismissedIds["a2"]).toBe(true);
  });

  it("read and dismissed state accumulate rather than overwrite each other", () => {
    useNotificationStore.getState().markRead("a1");
    useNotificationStore.getState().dismiss("a2");
    const state = useNotificationStore.getState();
    expect(state.readIds["a1"]).toBe(true);
    expect(state.dismissedIds["a2"]).toBe(true);
    expect(state.dismissedIds["a1"]).toBeUndefined();
    expect(state.readIds["a2"]).toBeUndefined();
  });
});

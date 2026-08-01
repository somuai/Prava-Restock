import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Restock waitlist", () => {
  it("opens the accessible waitlist dialog and restores focus when closed", async () => {
    const user = userEvent.setup();
    render(<App />);
    const trigger = screen.getByRole("button", { name: "Join the waitlist" });

    await user.click(trigger);
    expect(screen.getByRole("dialog", { name: "Join the waitlist." })).toBeVisible();
    await waitFor(() => expect(screen.getByLabelText("Email address")).toHaveFocus());

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it("shows inline validation for an invalid email without calling the API", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Join the waitlist" }));
    await user.type(screen.getByLabelText("Email address"), "not-an-email");
    await user.click(
      screen.getByRole("dialog").querySelector<HTMLButtonElement>('button[type="submit"]')!,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email address.");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("submits the email and reaches the truthful confirmation", async () => {
    const user = userEvent.setup();
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response(JSON.stringify({ status: "joined" }), { status: 200 }));
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Join the waitlist" }));
    await user.type(screen.getByLabelText("Email address"), "Pilot@Example.com");
    await user.click(
      screen.getByRole("dialog").querySelector<HTMLButtonElement>('button[type="submit"]')!,
    );

    expect(await screen.findByRole("heading", { name: "You’re in." })).toBeVisible();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0]?.[0]).toBe("/api/v1/waitlist");
    expect(JSON.parse(String(fetchSpy.mock.calls[0]?.[1]?.body))).toMatchObject({
      email: "pilot@example.com",
    });

    expect(screen.getByText(/when Restock is ready to try/i)).toBeVisible();
  });
});

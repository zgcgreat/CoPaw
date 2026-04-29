import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { HistorySessionRow } from "./HistorySessionRow";

vi.mock("../ChatSessionItem", () => ({
  __esModule: true,
  default: (props: { name: string; onClick?: () => void }) => (
    <button type="button" onClick={props.onClick}>
      {props.name}
    </button>
  ),
}));

describe("HistorySessionRow", () => {
  it("uses the resolved chat id as the click target when available", () => {
    const onSessionClick = vi.fn();

    render(
      <HistorySessionRow
        session={{
          id: "1777001065201000",
          realId: "chat-real-1",
          name: "running chat",
          messages: [],
          createdAt: "2026-04-24T00:00:00Z",
        }}
        active={false}
        onSessionClick={onSessionClick}
        onSessionDelete={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByText("running chat"));

    expect(onSessionClick).toHaveBeenCalledWith("chat-real-1");
  });
});

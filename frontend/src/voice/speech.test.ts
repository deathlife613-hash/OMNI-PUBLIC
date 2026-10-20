import { describe, expect, it } from "vitest";
import { chunkText, listenErrorMessage } from "./speech";

describe("chunkText", () => {
  it("returns nothing for empty text", () => expect(chunkText("  ")).toEqual([]));
  it("keeps short text whole", () => expect(chunkText("Hello there. How are you?")).toEqual(["Hello there. How are you?"]));
  it("splits long text on sentences within the limit", () => {
    const text = "One sentence here. ".repeat(30);
    const parts = chunkText(text, 100);
    expect(parts.length).toBeGreaterThan(3);
    expect(parts.every((p) => p.length <= 100)).toBe(true);
    expect(parts.join(" ").replace(/\s+/g, " ")).toContain("One sentence here.");
  });
  it("hard-splits a single oversized sentence", () => {
    expect(chunkText("a".repeat(500), 200).every((p) => p.length <= 200)).toBe(true);
  });
  it("does not read code blocks or markdown symbols aloud", () => {
    const out = chunkText("Run this:\n```\nrm -rf /\n```\n**Done**.").join(" ");
    expect(out).not.toContain("rm -rf");
    expect(out).not.toContain("**");
  });
});

describe("listenErrorMessage", () => {
  it("explains permission denial", () => expect(listenErrorMessage("not-allowed")).toMatch(/permission/i));
  it("stays silent on user abort", () => expect(listenErrorMessage("aborted")).toBe(""));
});

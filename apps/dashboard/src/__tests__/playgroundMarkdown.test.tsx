import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { renderMarkdown } from "../features/playground/markdown";

function Wrapper({ text }: { text: string }) {
  return <div>{renderMarkdown(text)}</div>;
}

describe("playground/markdown — renderMarkdown", () => {
  it("renders a fenced code block with a language label and copy button", () => {
    render(<Wrapper text={"Here:\n```python\nprint('hi')\n```"} />);
    expect(screen.getByText("python")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy code" })).toBeInTheDocument();
    expect(screen.getByText(/print/)).toBeInTheDocument();
  });

  it("renders a markdown table", () => {
    render(<Wrapper text={"| A | B |\n| --- | --- |\n| 1 | 2 |"} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("A")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("renders an unordered list", () => {
    render(<Wrapper text={"- first\n- second"} />);
    expect(screen.getByText("first")).toBeInTheDocument();
    expect(screen.getByText("second")).toBeInTheDocument();
    expect(document.querySelector("ul")).toBeInTheDocument();
  });

  it("renders bold, italic, and inline code", () => {
    render(<Wrapper text={"**bold** and *italic* and `code`"} />);
    expect(screen.getByText("bold").tagName).toBe("STRONG");
    expect(screen.getByText("italic").tagName).toBe("EM");
    expect(screen.getByText("code").tagName).toBe("CODE");
  });

  it("renders a heading and a horizontal rule", () => {
    render(<Wrapper text={"## Section\n\ntext\n\n---\n"} />);
    expect(screen.getByText("Section")).toBeInTheDocument();
    expect(document.querySelector("hr")).toBeInTheDocument();
  });
});

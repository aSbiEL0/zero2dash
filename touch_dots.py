import tkinter as tk


DOT_SIZE = 10


def main() -> None:
    root = tk.Tk()
    root.title("Touch Dots")
    root.configure(bg="white")
    root.attributes("-fullscreen", True)

    canvas = tk.Canvas(root, bg="white", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    def draw_dot(event: tk.Event) -> None:
        half = DOT_SIZE // 2
        canvas.create_oval(
            event.x - half,
            event.y - half,
            event.x + half,
            event.y + half,
            fill="black",
            outline="black",
        )

    canvas.bind("<Button-1>", draw_dot)
    canvas.bind("<B1-Motion>", draw_dot)
    root.bind("<Escape>", lambda _event: root.destroy())

    root.mainloop()


if __name__ == "__main__":
    main()

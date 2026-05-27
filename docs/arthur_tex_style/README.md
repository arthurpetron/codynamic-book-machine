# Arthur TeX Style

Personal LaTeX document style centered on `arthur-book.cls`.

## Structure

```text
arthur_tex_style/
  arthur-book.cls
  tex/
    arthur-symbols.sty
    arthur-notation.sty
    arthur-margin-citations.sty
    arthur-figures.sty
    arthur-tikz.sty
  assets/
    codynamic_mark.tikz.def
  examples/
    minimal.tex
    shortcite-demo.tex
    references.bib
    pdf/
```

## Class

Use the class from a document in this folder:

```tex
\documentclass[wide-notes]{arthur-book}
```

Available options:

- `tight`: compact margins; currently the default.
- `print`: comfortable book-style margins.
- `wide-notes`: wider outer margin for margin notes and citations.

## Modules

`arthur-book.cls` is the public entry point. It loads focused helper modules from `tex/`:

- `arthur-symbols`: core math notation commands.
- `arthur-math`: numbered displays, full-width equations, equation summaries, and TikZ-CD category diagrams.
- `arthur-notation`: notation environments and margin keys.
- `arthur-margin-citations`: compact `\shortcite` margin citations.
- `arthur-figures`: `mainfigure`, `marginfigure`, and `fullfigure` environments.
- `arthur-tikz`: TikZ helpers and marks.

## Math

Equations are numbered by chapter, section, and equation, e.g. `(1.2.3)`.
Number tags are typeset in the margin for normal displays.

```tex
\begin{equation}
  C = 2\pi r
  \label{eq:circumference}
\end{equation}

\equationsummary{
  \equationterm{\pi}{the ratio between circumference and diameter of a circle.}
  \equationterm{r}{the radius of the circle.}
}
```

The summary command is named `\equationsummary` rather than
`\equation_summary` because `_` is reserved for subscripts in ordinary LaTeX
documents.

Use the optional `margin` placement when the explanation should sit beside the
display instead of in the main text flow:

```tex
\equationsummary[margin]{
  \equationterm{\pi}{the ratio between circumference and diameter of a circle.}
  \equationterm{r}{the radius of the circle.}
}
```

Margin summaries are shifted down slightly by default so they do not collide
with the preceding equation number. They also reserve their own height in the
main text flow, preventing later equation numbers from landing inside the
summary. Tune the offset in a document with:

```tex
\setlength{\arthurequationsummarymarginoffset}{2\baselineskip}
```

Use `break_equation` when you want a deliberate line break. Put `&` at the
alignment point and `\eqbreak` where the display should continue.

```tex
\begin{break_equation}[eq:long]
  F(x) &= a_0 + a_1x + a_2x^2 + a_3x^3
  \eqbreak
       + a_4x^4 + a_5x^5 .
\end{break_equation}
```

Use `full_equation` for long displays that should span the text column and
margin column. Equation numbers still stay in the margin.

```tex
\begin{full_equation}[eq:full]
  G(x) &= \sum_{i=0}^{n} a_i x^i
       + \int_0^1 K(x,t)h(t)\,dt .
\end{full_equation}
```

Category theory diagrams use TikZ-CD inside numbered equation wrappers. This
keeps diagram syntax standard while preserving equation labels and references.

```tex
\begin{cat_math}[eq:pullback][row sep=large,column sep=large]
  P \arrow[r] \arrow[d] & X \arrow[d, "f"] \\
  Y \arrow[r, "g"'] & Z
\end{cat_math}
```

For wide category diagrams, use `full_cat_math` with the same syntax.

## Theorems And Math Helpers

The class defines theorem-like environments with section-based numbering:

```tex
\begin{theorem}
Every compact metric space is complete and totally bounded.
\end{theorem}

\begin{definition}
A morphism \(f:X\to Y\) is monic if ...
\end{definition}
```

Available environments are `theorem`, `lemma`, `proposition`, `corollary`,
`definition`, and `example`. Definitions and examples are upright; the rest use
italic body text. Proofs are provided by `amsthm`.

Common paired delimiters are available via `mathtools`:

```tex
\abs{x}       \abs*{\frac{x}{y}}
\norm{v}      \inner{x,y}
\paren{x+1}   \bracket{0,1}
\braces{x}    \set{x}{P(x)}
```

Equation annotation helpers:

```tex
a &\defeq b + c \eqby{definition} \\
  &= \underannotate{b}{known term} + c .
```

Use `localnotation` for symbols whose meaning is local to a proof, section, or
calculation:

```tex
\begin{localnotation}
  \notationitem{\Delta}{a small change in the current variable.}
  \notationitem{\Phi}{the local potential function.}
\end{localnotation}
```

Use `infobox` for short contextual notes:

```tex
\begin{infobox}[title=Reading note]
This argument only uses compactness at the final step.
\end{infobox}
```

The default infobox is main-column width. Use the first optional argument for
placement, and the second optional argument for `tcolorbox` options:

```tex
\begin{infobox}[full][title=Wide note]
This note spans the main column and margin column.
\end{infobox}

\begin{infobox}[margin][title=Aside]
This note sits in the right margin.
\end{infobox}
```

## Figures

The class provides three figure environments for the Tufte-style layout:

```tex
\begin{mainfigure}
  \includegraphics[width=\textwidth]{image}
  \caption{Main-column figure.}
\end{mainfigure}

\begin{marginfigure}
  \includegraphics[width=\marginparwidth]{image}
  \caption{Margin figure.}
\end{marginfigure}

\begin{fullfigure}
  \includegraphics[width=\arthurfullwidth]{image}
  \caption{Full-width figure.}
\end{fullfigure}
```

## Short Citations

`\shortcite{key}` requires `biblatex`; the document chooses its own bibliography style and backend.

```tex
\usepackage[backend=biber,style=authoryear]{biblatex}
\addbibresource{references.bib}

Text with a margin citation.\shortcite{doe2024}
Text with context.\shortcite[See also]{doe2024}[ch. 2]
```

The command prints a compact margin note with title and author, registers the key with `\nocite`, and emits approximate margin crowding warnings when many margin citations accumulate on a page.

## Examples

Compile the examples from the project root:

```sh
mkdir -p examples/pdf
pdflatex -output-directory=examples/pdf examples/minimal.tex
pdflatex -output-directory=examples/pdf examples/minimal.tex
pdflatex -output-directory=examples/pdf examples/shortcite-demo.tex
biber examples/pdf/shortcite-demo
pdflatex -output-directory=examples/pdf examples/shortcite-demo.tex
pdflatex -output-directory=examples/pdf examples/shortcite-demo.tex
```

The generated PDFs will be written to `examples/pdf/`.

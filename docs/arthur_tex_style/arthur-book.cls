% !TEX root = arthur-book.cls
% !TEX encoding = UTF-8 Unicode
% arthur-book.cls
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{arthur-book}[2025/09/03 Arthur's constructive book class]

% ---------- Options ----------
\newif\ifarthur@tight
\newif\ifarthur@print
\newif\ifarthur@widenotes
\DeclareOption{tight}{\arthur@tighttrue\arthur@printfalse\arthur@widenotesfalse}
\DeclareOption{print}{\arthur@tightfalse\arthur@printtrue\arthur@widenotesfalse}
\DeclareOption{wide-notes}{\arthur@tightfalse\arthur@printfalse\arthur@widenotestrue}
\DeclareOption*{} % ignore unknown
\ExecuteOptions{tight} % default
\ProcessOptions\relax

% ---------- Base class ----------
% Keep it flexible: book, but openany, twoside so we control paging & headers.
\LoadClass[11pt,openany,twoside]{book}

% ---------- Required packages ----------
\RequirePackage{etoolbox}
\RequirePackage{geometry}
\RequirePackage{fancyhdr}
\RequirePackage{titlesec}
\RequirePackage{titletoc}
\RequirePackage{microtype}
\RequirePackage{ifthen}
\RequirePackage{calc}
\RequirePackage{amsmath}
\RequirePackage{amssymb}
\RequirePackage{mathtools}
\RequirePackage{hyperref}
\hypersetup{hidelinks}

% ---------- Geometry presets ----------
% tight  : ~36pt side margins, compact top/bottom
% print  : comfortable book-ish margins
% wide-notes : Tufte-like outer margin for sidenotes
\ifarthur@tight
  \geometry{
    paperwidth=8.5in,paperheight=11in,
    inner=36pt, outer=36pt,
    top=36pt, bottom=48pt,
    headheight=18pt, headsep=18pt, footskip=18pt,
    includehead, includefoot
  }
\fi
\ifarthur@print
  \geometry{
    paperwidth=8.5in,paperheight=11in,
    inner=28mm, outer=32mm,
    top=24mm, bottom=28mm,
    headheight=18pt, headsep=18pt, footskip=20pt,
    includehead, includefoot
  }
\fi
\ifarthur@widenotes
  % Tufte-like letterpaper layout:
  % textwidth=26pc, marginparsep=2pc, marginparwidth=12pc.
  \geometry{
    letterpaper,
    left=1in,
    top=1in,
    textwidth=26pc,
    marginparsep=2pc,
    marginparwidth=12pc,
    textheight=44\baselineskip,
    headheight=\baselineskip,
    headsep=2\baselineskip,
    footskip=2\baselineskip,
    asymmetric
  }
\makeatletter
  \@mparswitchfalse
\makeatother
\fi

% ---------- Depth of numbering (Arthur wants details!) ----------
\setcounter{secnumdepth}{6}
\setcounter{tocdepth}{6}

% ---------- Remove forced page clears around \chapter ----------
\makeatletter
\pretocmd{\chapter}{\@afterindentfalse}{}{}
\patchcmd{\chapter}{\if@openright\cleardoublepage\else\clearpage\fi}{}{}{}
\patchcmd{\@chapter}{\clearpage}{}{}{}
\patchcmd{\@schapter}{\clearpage}{}{}{}
\makeatother

% ---------- Chapter/Section formatting ----------
\titleformat{\chapter}[hang]
  {\huge\bfseries}
  {\thechapter\;\;\rule[-0.3ex]{.5pt}{1.25em}}
  {1em}
  {\Huge}
  [\vspace{0.5ex}\rule{\textwidth}{0.5pt}\vspace{0.75ex}]
\titlespacing*{\chapter}{0pt}{1.2ex plus .3ex}{1.0ex}

\titleformat{\section}[hang]
  {\Large\bfseries}
  {\thesection}{0.6em}{}
\titlespacing*{\section}{0pt}{1.0ex plus .2ex}{0.5ex}

\titleformat{\subsection}[hang]
  {\large\bfseries}
  {\thesubsection}{0.5em}{}
\titlespacing*{\subsection}{0pt}{0.8ex plus .2ex}{0.4ex}

\titleformat{\subsubsection}[runin]
  {\normalsize\bfseries}
  {\thesubsubsection}{0.5em}{}[.]

% ---------- TOC: compact dotted leaders ----------
\contentsmargin{2em}
\dottedcontents{chapter}[0em]{}{\dimexpr1.5em+1.5ex}{0.8em}
\dottedcontents{section}[1.6em]{}{\dimexpr2.3em+1.5ex}{0.8em}
\dottedcontents{subsection}[3.2em]{}{\dimexpr3.1em+1.5ex}{0.8em}
\dottedcontents{subsubsection}[4.8em]{}{\dimexpr3.9em+1.5ex}{0.8em}
\dottedcontents{subsubsubsection}[6.4em]{}{\dimexpr4.7em+1.5ex}{0.8em}

% ---------- Header path: chapter --> section --> subsection ----------
% We'll track current chapter/section/subsection titles and compose a path.
\makeatletter
\newcommand*\arthur@chapname{}
\newcommand*\arthur@secname{}
\newcommand*\arthur@subsecname{}
\newcommand*\arthur@subsubsecname{}
\newcommand*\arthur@subsubsubsecname{}
\renewcommand{\chaptermark}[1]{%
  \gdef\arthur@chapname{#1}%
  \gdef\arthur@secname{}%
  \gdef\arthur@subsecname{}%
  \gdef\arthur@subsubsecname{}%
  \gdef\arthur@subsubsubsecname{}%
}
\renewcommand{\sectionmark}[1]{%
  \gdef\arthur@secname{#1}%
  \gdef\arthur@subsecname{}%
  \gdef\arthur@subsubsecname{}%
  \gdef\arthur@subsubsubsecname{}%
}
\renewcommand{\subsectionmark}[1]{%
  \gdef\arthur@subsecname{#1}%
  \gdef\arthur@subsubsecname{}%
  \gdef\arthur@subsubsubsecname{}%
}
\renewcommand{\subsubsectionmark}[1]{%
  \gdef\arthur@subsubsecname{#1}%
  \gdef\arthur@subsubsubsecname{}%
}
\newcommand{\subsubsubsectionmark}[1]{\gdef\arthur@subsubsubsecname{#1}}
\newcommand{\arthur@path}{%
  \ifx\arthur@chapname\@empty\else \arthur@chapname\fi
  \ifx\arthur@secname\@empty\else \,{\footnotesize$\rightarrow$}\, \arthur@secname\fi
  \ifx\arthur@subsecname\@empty\else \,{\footnotesize$\rightarrow$}\, \arthur@subsecname\fi
  \ifx\arthur@subsubsecname\@empty\else \,{\footnotesize$\rightarrow$}\, \arthur@subsubsecname\fi
  \ifx\arthur@subsubsubsecname\@empty\else \,{\footnotesize$\rightarrow$}\, \arthur@subsubsubsecname\fi
}
\makeatother

% ---------- Page number box helper ----------
\makeatletter
\newcommand{\arthur@pagebox}{%
  \begingroup
  \setlength\fboxsep{2pt}%
  \setlength\fboxrule{0.4pt}%
  \fbox{\normalsize\thepage}%
  \endgroup
}

% ---------- Full-bleed header rule (2pt inset from paper edges) ----------
% We'll draw across paper width minus 4pt, shifted left by (oddsidemargin+1in-2pt).
\newcommand{\arthur@headrule}{%
  \vspace*{-\dimexpr\baselineskip-1.6ex}%
  \makebox[0pt][l]{%
    \hspace*{\dimexpr -\oddsidemargin-1in+2pt}%
    \rule{\dimexpr \paperwidth-4pt}{0.4pt}%
  }%
  \vspace*{1.2ex}%
}
\newcommand{\arthur@headerlabel}{\raisebox{0.45ex}{\textsc{\small \arthur@path}}}

% ---------- Headers/footers ----------
\pagestyle{fancy}
\fancyhf{} % clear

% Left (even) pages: page box at absolute left; Right (odd) pages: at absolute right.
% We compute edge-aligned placements using \makebox[0pt] and hspace offsets from text origin.
\fancyhead[LE]{%
  % Page box 2pt from left paper edge:
  \makebox[0pt][l]{\hspace*{\dimexpr -\evensidemargin-1in+2pt}\arthur@pagebox}%
  \quad\arthur@headerlabel
  \arthur@headrule
}
\fancyhead[RO]{%
  % Page box 2pt from right paper edge:
  \makebox[0pt][r]{\hspace*{\dimexpr \textwidth+\oddsidemargin+1in-2pt}\arthur@pagebox}%
  \arthur@headerlabel
  \arthur@headrule
}
% Keep each page to one path header; duplicating both inner and outer headers
% makes long section paths collide in the compact layouts.
\fancyhead[LO]{}
\fancyhead[RE]{}

% Footer: simple centered page number (redundant but handy)
\fancyfoot[C]{\thepage}
\renewcommand{\headrulewidth}{0pt}
\renewcommand{\footrulewidth}{0pt}
\makeatother

% ---------- Title page ----------
\makeatletter
\ifarthur@widenotes
\newcommand{\arthur@fullwidth@geometry}{%
  \newgeometry{
    left=1in,
    right=1in,
    top=1in,
    bottom=1in,
    headheight=\baselineskip,
    headsep=2\baselineskip,
    footskip=2\baselineskip
  }%
}
  \let\arthur@book@maketitle\maketitle
  \renewcommand{\maketitle}{%
    \arthur@fullwidth@geometry
    \arthur@book@maketitle
    \restoregeometry
  }%
  \let\arthur@book@tableofcontents\tableofcontents
  \renewcommand{\tableofcontents}{%
    \clearpage
    \arthur@fullwidth@geometry
    \arthur@book@tableofcontents
    \clearpage
    \restoregeometry
  }%
\fi
\makeatother

% ---------- Arthur modules ----------
\RequirePackage{tex/arthur-symbols}
\RequirePackage{tex/arthur-math}
\RequirePackage{tex/arthur-notation}
\RequirePackage{tex/arthur-margin-citations}
\RequirePackage{tex/arthur-figures}
\RequirePackage{tex/arthur-tikz}

% ---------- End class ----------

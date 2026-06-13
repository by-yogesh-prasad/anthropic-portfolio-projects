"""Click CLI for GitMind — index, ask, status, clear commands."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from gitmind.embedder import embed_one
from gitmind.indexer import index_repo
from gitmind.schema import IndexMeta
from gitmind.store import clear_all, count, init_db, search

console = Console()
err_console = Console(stderr=True)

GITMIND_DIR = Path.home() / ".gitmind"
MODEL = "claude-sonnet-4-6"


def _repo_dir(repo_name: str) -> Path:
    return GITMIND_DIR / repo_name


def _db_path(repo_name: str) -> Path:
    return _repo_dir(repo_name) / "index.db"


def _meta_path(repo_name: str) -> Path:
    return _repo_dir(repo_name) / "meta.json"


def _save_meta(meta: IndexMeta) -> None:
    path = _meta_path(meta.repo_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(meta.model_dump_json(indent=2))


def _load_meta(repo_name: str) -> IndexMeta | None:
    path = _meta_path(repo_name)
    if not path.exists():
        return None
    return IndexMeta.model_validate_json(path.read_text())


def _find_indexed_repos() -> list[str]:
    if not GITMIND_DIR.exists():
        return []
    return [
        d.name
        for d in GITMIND_DIR.iterdir()
        if d.is_dir() and _meta_path(d.name).exists()
    ]


@click.group()
def cli() -> None:
    """GitMind — ask natural language questions about your Git history."""


@cli.command()
@click.option("--repo", default=".", show_default=True, help="Path to git repository.")
def index(repo: str) -> None:
    """Index a Git repository into the local vector store."""
    repo_path = Path(repo).resolve()
    if not repo_path.exists():
        err_console.print(f"[red]Error:[/] path does not exist: {repo_path}")
        raise SystemExit(1)

    try:
        from git import Repo as GitRepo  # local import to keep startup fast

        git_repo = GitRepo(str(repo_path), search_parent_directories=True)
        repo_name = Path(git_repo.working_dir).name
    except Exception as exc:
        err_console.print(f"[red]Error:[/] could not open git repository: {exc}")
        raise SystemExit(1)

    db_path = _db_path(repo_name)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        meta = index_repo(repo_path, db_path)
    except ValueError as exc:
        err_console.print(f"[red]Error:[/] {exc}")
        raise SystemExit(1)

    _save_meta(meta)
    console.print(
        f"[bold green]Done![/] Indexed [bold]{meta.total_commits:,}[/] commits from "
        f"[bold]{meta.repo_name}[/] → [dim]{db_path}[/dim]"
    )


@cli.command()
@click.argument("question")
@click.option(
    "--repo",
    default=None,
    help="Repository name (auto-detected when only one is indexed).",
)
@click.option("--top-k", default=10, show_default=True, help="Chunks to retrieve.")
def ask(question: str, repo: str | None, top_k: int) -> None:
    """Ask a natural language question about your indexed Git history."""
    import anthropic

    # Resolve which repo to query
    if repo is None:
        repos = _find_indexed_repos()
        if not repos:
            err_console.print(
                "[red]Error:[/] no indexed repositories found. "
                "Run [bold]gitmind index[/] first."
            )
            raise SystemExit(1)
        if len(repos) > 1:
            err_console.print(
                f"[red]Error:[/] multiple repositories indexed: {repos}. "
                "Use [bold]--repo NAME[/] to select one."
            )
            raise SystemExit(1)
        repo = repos[0]

    meta = _load_meta(repo)
    if meta is None:
        err_console.print(f"[red]Error:[/] no index found for repository '{repo}'.")
        raise SystemExit(1)

    db_path = _db_path(repo)
    if not db_path.exists():
        err_console.print(f"[red]Error:[/] index database missing at {db_path}.")
        raise SystemExit(1)

    # Embed query and retrieve nearest chunks
    with console.status("[bold green]Searching index…", spinner="dots"):
        query_embedding = embed_one(question)
        conn = init_db(db_path)
        results = search(conn, query_embedding, top_k=top_k)
        conn.close()

    if not results:
        console.print("[yellow]No relevant commits found in the index.[/]")
        return

    # Build grounded context for Claude
    context_blocks: list[str] = []
    for r in results:
        sha_short = r["commit_sha"][:8]
        context_blocks.append(f"[Commit {sha_short}]\n{r['text']}")

    context = "\n\n---\n\n".join(context_blocks)

    system_prompt = (
        "You are GitMind, an expert at explaining Git repository history. "
        "You answer questions about why code exists, when decisions were made, "
        "and the reasoning behind changes — all based on commit messages and diffs. "
        "Always cite the commit SHA (the 8-character prefix shown in brackets) when "
        "referencing a specific change. Format your answer in Markdown."
    )

    user_message = (
        f"Repository: {repo}\n\n"
        f"Question: {question}\n\n"
        f"Relevant commits from the repository history:\n\n{context}"
    )

    with console.status("[bold green]Asking Claude…", spinner="dots"):
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

    answer = next(
        (block.text for block in response.content if block.type == "text"), ""
    )

    console.print()
    console.print(
        Panel(
            Markdown(answer),
            title="[bold cyan]GitMind Answer[/]",
            border_style="cyan",
        )
    )
    console.print(
        f"\n[dim]Retrieved {len(results)} chunks · "
        f"{response.usage.input_tokens} input tokens · "
        f"{response.usage.output_tokens} output tokens[/dim]"
    )


@cli.command()
@click.option("--repo", default=None, help="Repository name (shows all if omitted).")
def status(repo: str | None) -> None:
    """Show index statistics for one or all repositories."""
    repos = [repo] if repo else _find_indexed_repos()

    if not repos:
        console.print("[yellow]No indexed repositories found.[/]")
        return

    table = Table(
        title="GitMind Index Status",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Repository", style="bold")
    table.add_column("Commits", justify="right")
    table.add_column("Chunks", justify="right")
    table.add_column("Indexed At")
    table.add_column("Database", style="dim")

    for repo_name in repos:
        meta = _load_meta(repo_name)
        if meta is None:
            table.add_row(repo_name, "?", "?", "?", "?")
            continue

        chunk_count = "?"
        db = _db_path(repo_name)
        if db.exists():
            try:
                conn = init_db(db)
                chunk_count = f"{count(conn):,}"
                conn.close()
            except Exception:
                pass

        indexed_at = meta.indexed_at.astimezone().strftime("%Y-%m-%d %H:%M")
        table.add_row(
            meta.repo_name,
            f"{meta.total_commits:,}",
            chunk_count,
            indexed_at,
            str(db),
        )

    console.print(table)


@cli.command()
@click.option(
    "--repo",
    default=None,
    help="Repository name to clear (required when multiple are indexed).",
)
@click.option("--yes", is_flag=True, help="Skip confirmation prompt.")
def clear(repo: str | None, yes: bool) -> None:
    """Clear all indexed data for a repository."""
    if repo is None:
        repos = _find_indexed_repos()
        if not repos:
            console.print("[yellow]No indexed repositories found.[/]")
            return
        if len(repos) > 1:
            err_console.print(
                f"[red]Error:[/] multiple repositories indexed: {repos}. "
                "Use [bold]--repo NAME[/] to select one."
            )
            raise SystemExit(1)
        repo = repos[0]

    if _load_meta(repo) is None:
        err_console.print(f"[red]Error:[/] no index found for repository '{repo}'.")
        raise SystemExit(1)

    if not yes:
        click.confirm(
            f"Clear all indexed data for '{repo}'? This cannot be undone.",
            abort=True,
        )

    db = _db_path(repo)
    if db.exists():
        try:
            conn = init_db(db)
            clear_all(conn)
            conn.close()
            db.unlink()
        except Exception as exc:
            err_console.print(f"[yellow]Warning:[/] could not clear database: {exc}")

    meta = _meta_path(repo)
    if meta.exists():
        meta.unlink()

    try:
        _repo_dir(repo).rmdir()
    except OSError:
        pass

    console.print(f"[bold green]Cleared[/] index for '[bold]{repo}[/]'.")


@cli.command()
@click.option("--host", default="0.0.0.0", show_default=True, help="Bind host.")
@click.option("--port", default=8000, show_default=True, help="Bind port.")
@click.option("--reload", is_flag=True, help="Enable auto-reload (development).")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the GitMind API server (backend for the Next.js UI)."""
    try:
        import uvicorn
    except ImportError:
        err_console.print(
            "[red]Error:[/] uvicorn not installed. Run: "
            "[bold]pip install 'gitmind[api]'[/]"
        )
        raise SystemExit(1)

    console.print(
        f"[bold cyan]GitMind API[/] starting on [bold]http://{host}:{port}[/] "
        + ("[dim](reload enabled)[/dim]" if reload else "")
    )
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload,
        app_dir=str(Path(__file__).parent.parent),
    )

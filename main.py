#!/usr/bin/env python3
"""
Main entry point for the Codynamic Book Machine.

This script demonstrates proper bootstrap usage and provides
a command-line interface to the system.
"""

import sys
import argparse
import json
from pathlib import Path

from scripts.bootstrap import BootstrapSystem, BootstrapError, BootPhase


def cmd_bootstrap(args):
    """Bootstrap the system and show status."""
    try:
        print("Bootstrapping Codynamic Book Machine...\n")
        
        system = BootstrapSystem.auto_bootstrap(verbose=args.verbose)
        
        print()
        system.print_status()
        
        if system.config.current_phase == BootPhase.READY:
            print("✓ System is READY")
            return 0
        else:
            print("✗ System is NOT ready")
            return 1
    
    except BootstrapError as e:
        print(f"\n✗ Bootstrap failed: {e}")
        for error in e.errors:
            print(f"  - {error}")
        return 1


def cmd_status(args):
    """Show system status without full bootstrap."""
    system = BootstrapSystem()
    system.phase_0_seed()
    system.phase_1_discovery()
    
    system.print_status()
    return 0


def cmd_validate_outline(args):
    """Validate an outline file."""
    try:
        # Bootstrap first
        if not args.skip_bootstrap:
            print("Bootstrapping system...")
            system = BootstrapSystem.auto_bootstrap(verbose=False)
            print()
        
        # Now validate
        from scripts.agents.outline_agent import OutlineAgent
        
        outline_path = Path(args.outline)
        if not outline_path.exists():
            print(f"✗ Outline not found: {outline_path}")
            return 1
        
        print(f"Validating outline: {outline_path}\n")
        
        agent = OutlineAgent(outline_path)
        is_valid = agent.run(verbose=True)
        
        return 0 if is_valid else 1
    
    except Exception as e:
        print(f"✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def cmd_registry(args):
    """Show schema registry information."""
    try:
        # Minimal bootstrap
        if not args.skip_bootstrap:
            system = BootstrapSystem.bootstrap_to_phase(
                BootPhase.DISCOVERY, 
                verbose=False
            )
        
        from scripts.utils.schema_registry import get_registry
        
        registry = get_registry()
        registry.print_registry_summary()
        
        return 0
    
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1


def cmd_intake(args):
    """Run one conversational intake action against a book root."""
    try:
        from scripts.book import BookIntakeService, BookRepository

        book_root = Path(args.book_root)
        repository = BookRepository(book_root)

        if args.intake_command == "init":
            service = BookIntakeService()
            if args.title:
                service.record_answer("title", args.title)
            repository.save_book(service.book)
            print(f"Initialized intake book at {repository.outline_path}")
            question = service.next_question()
            if question:
                print(f"Next question [{question.id}]: {service.socratic_prompt(question.id)}")
            return 0

        if args.intake_command == "next":
            service = repository.intake_service()
            question = service.next_question()
            if not question:
                print("Intake is complete. Generate the initial plan when ready.")
                return 0
            print(f"[{question.id}] {service.socratic_prompt(question.id)}")
            print(f"Rationale: {question.rationale}")
            return 0

        if args.intake_command == "answer":
            book = repository.record_intake_answer(args.question_id, args.answer)
            service = BookIntakeService(book)
            progress = service.progress()
            print(
                "Recorded answer. "
                f"Required progress: {progress['required_answered']}/{progress['required_total']}"
            )
            next_question = service.next_question()
            if next_question:
                prompt = service.socratic_prompt(next_question.id)
                print(f"Next question [{next_question.id}]: {prompt}")
            return 0

        if args.intake_command == "plan":
            book = repository.generate_initial_plan()
            plan = book["work"]["intake"]["plan"]
            print(f"Generated initial plan with {len(book['work']['structure'])} chapters.")
            if plan["open_questions"]:
                print("Open questions:")
                for question in plan["open_questions"]:
                    print(f"- {question['question_id']}: {question['question']}")
            return 0

        print("Unknown intake command")
        return 1

    except Exception as e:
        print(f"✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def cmd_import(args):
    """Import external artifacts into canonical book projects."""
    try:
        from scripts.book import BookImporter, BookLibrary

        if args.import_command == "outline":
            if args.register:
                record, result = BookLibrary(args.book_data_dir).import_outline(
                    args.input,
                    book_root=args.book_root,
                    use_llm=args.use_llm,
                )
                print(f"Imported outline: {result.title} ({record.book_id})")
                print(f"Book root: {result.book_root}")
                print(f"Outline: {result.outline_path}")
                print(f"Report: {result.report_path}")
                return 0
            importer = BookImporter(args.book_data_dir)
            result = importer.import_outline(
                args.input,
                book_root=args.book_root,
                use_llm=args.use_llm,
            )
            print(f"Imported outline: {result.title} ({result.work_id})")
            print(f"Book root: {result.book_root}")
            print(f"Outline: {result.outline_path}")
            print(f"Report: {result.report_path}")
            return 0

        print("Unknown import command")
        return 1

    except Exception as e:
        print(f"✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def cmd_authoring(args):
    """Run authoring-loop actions against a book root."""
    try:
        from scripts.book import AuthoringLoop, CommunicationMemory

        if args.authoring_command == "memory":
            memory = CommunicationMemory(args.data_root).build()
            print(f"Built log memory from {memory['message_count']} messages and {memory['user_question_count']} user questions.")
            return 0

        loop = AuthoringLoop(args.book_root, mode=getattr(args, "mode", "proposal"))

        if args.authoring_command == "propose-section":
            content = Path(args.content_file).read_text() if args.content_file else args.content
            proposal = loop.propose_section_draft(
                section_id=args.section_id,
                content=content,
                agent_id=args.agent_id,
                rationale=args.rationale,
                extension=args.extension,
            )
            print(f"Created proposal {proposal.proposal_id} for {proposal.target_path}")
            print(f"Status: {loop.proposals.load(proposal.proposal_id).status}")
            return 0

        if args.authoring_command == "accept":
            proposal = loop.proposals.accept(args.proposal_id, reviewer=args.reviewer, note=args.note)
            print(f"Accepted proposal {proposal.proposal_id} -> {proposal.target_path}")
            return 0

        if args.authoring_command == "reject":
            proposal = loop.proposals.reject(args.proposal_id, reviewer=args.reviewer, note=args.note)
            print(f"Rejected proposal {proposal.proposal_id}")
            return 0

        if args.authoring_command == "media-request":
            request = loop.media.request_media(
                section_id=args.section_id,
                requesting_agent=args.requesting_agent,
                description=args.description,
                media_type=args.media_type,
            )
            print(f"Created media request {request['request_id']} for {request['section_id']}")
            return 0

        if args.authoring_command == "media-fulfill":
            content = Path(args.content_file).read_text() if args.content_file else args.content
            request = loop.media.fulfill_request(
                request_id=args.request_id,
                diagram_agent=args.diagram_agent,
                content=content,
                extension=args.extension,
            )
            print(f"Fulfilled media request {request['request_id']} -> {request['path']}")
            return 0

        if args.authoring_command == "check":
            event = loop.record_gardener_check(
                section_id=args.section_id,
                intent=args.intent,
                dependencies=args.dependencies,
                claim_clarity=args.claim_clarity,
                latex=args.latex,
                rationale=args.rationale,
            )
            print(f"Recorded gardener check {event['event_id']} with status {event['status']}")
            return 0

        print("Unknown authoring command")
        return 1

    except Exception as e:
        print(f"✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def cmd_typeset(args):
    """Run document assembly, style, compile, and export actions."""
    try:
        from scripts.book import BookRepository, DocumentStyleRegistry, LatexBuildService

        if args.typeset_command == "styles":
            styles = DocumentStyleRegistry(Path(".")).list_styles()
            for style in styles:
                print(f"{style.style_id}\t{style.label}\t{style.description}")
            return 0

        repository = BookRepository(Path(args.book_root))

        if args.typeset_command == "set-style":
            settings = repository.design_settings(project_root=Path(".")).update({"style_id": args.style_id})
            print(f"Document style set to {settings['style_id']}")
            return 0

        builder = LatexBuildService(args.book_root, project_root=Path("."))

        if args.typeset_command == "assemble":
            tex = builder.assembler.assemble_section(args.section_id) if args.section_id else builder.assembler.assemble_book()
            output = Path(args.output) if args.output else Path(args.book_root) / "build" / "tex" / "assembled.tex"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(tex)
            print(f"Assembled TeX: {output}")
            return 0

        if args.typeset_command == "compile":
            result = (
                builder.compile_section(args.section_id, engine=args.engine)
                if args.section_id
                else builder.compile_book(engine=args.engine)
            )
            print(f"Compile status: {result.status}")
            print(f"TeX: {result.tex_path}")
            if result.pdf_path:
                print(f"PDF: {result.pdf_path}")
            print(f"Log: {result.log_path}")
            if result.errors:
                print("Errors:")
                for error in result.errors:
                    print(f"- {error}")
            return 0 if result.status == "passed" else 1

        if args.typeset_command == "export-html":
            output = builder.export_html()
            print(f"HTML export: {output}")
            return 0

        print("Unknown typeset command")
        return 1

    except Exception as e:
        print(f"✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def cmd_app(args):
    """Desktop app JSON API used by Electron IPC."""
    try:
        from scripts.book import BookAppState, BookLibrary

        library = BookLibrary(args.book_data_dir)

        if args.app_command == "library":
            payload = {
                "active": library.active().book_id if library.list_books(refresh=True) else None,
                "books": [record.__dict__ for record in library.list_books()],
            }
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        if args.app_command == "open-book":
            payload = library.open_book(args.book_id).__dict__
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        if args.app_command == "new-book":
            tags = [tag.strip() for tag in (args.tags or "").split(",") if tag.strip()]
            payload = library.create_book(args.title, book_id=args.book_id, tags=tags).__dict__
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        if args.app_command == "archive-book":
            payload = library.archive_book(args.book_id).__dict__
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        book_root = Path(args.book_root) if args.book_root else (
            Path(library.get(args.book_id).root) if args.book_id else library.active_root()
        )
        app_state = BookAppState(book_root, data_root=args.data_root)

        if args.app_command == "state":
            payload = app_state.snapshot(selected_id=args.selected_id)
        elif args.app_command == "section":
            payload = app_state.section_payload(args.section_id)
        elif args.app_command == "save-section":
            content = Path(args.content_file).read_text()
            payload = app_state.save_section(args.section_id, content)
        elif args.app_command == "compile-section":
            payload = app_state.compile_section(args.section_id)
        elif args.app_command == "compile-book":
            payload = app_state.compile_book()
        elif args.app_command == "request-review":
            payload = app_state.request_review(subject=args.subject)
        elif args.app_command == "create-section":
            payload = app_state.create_section(args.title, parent_id=args.parent_id)
        elif args.app_command == "create-chapter":
            payload = app_state.create_chapter(args.title)
        elif args.app_command == "update-outline-node":
            payload = app_state.update_outline_node(args.node_id, args.title)
        elif args.app_command == "accept-proposal":
            payload = app_state.accept_proposal(args.proposal_id, note=args.note)
        elif args.app_command == "reject-proposal":
            payload = app_state.reject_proposal(args.proposal_id, note=args.note)
        elif args.app_command == "revise-proposal":
            content = Path(args.content_file).read_text()
            payload = app_state.revise_proposal(args.proposal_id, proposed_content=content, note=args.note)
        else:
            raise ValueError(f"Unknown app command: {args.app_command}")

        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def cmd_beyond(args):
    """Run beyond-MVP graph, creative, and versioning actions."""
    try:
        from scripts.book import (
            ArtworkSpec,
            BookRepository,
            ChangeSetManager,
            DiagramSpec,
        )

        if args.beyond_command == "changeset":
            manager = ChangeSetManager(Path("."))
            changeset = manager.create(
                title=args.title,
                agent_id=args.agent_id,
                files=args.files,
                branch_name=args.branch_name,
            )
            print(json.dumps(changeset.__dict__, indent=2, sort_keys=True))
            return 0

        repository = BookRepository(Path(args.book_root))

        if args.beyond_command == "graph":
            print(json.dumps(repository.knowledge_graph().analyze().as_dict(), indent=2, sort_keys=True))
            return 0

        if args.beyond_command == "diagram":
            spec_payload = json.loads(Path(args.spec).read_text())
            spec = DiagramSpec(
                diagram_id=spec_payload["diagram_id"],
                title=spec_payload["title"],
                linguistic_description=spec_payload["linguistic_description"],
                computational_definition=spec_payload.get("computational_definition", {}),
                section_id=spec_payload.get("section_id"),
                caption=spec_payload.get("caption", ""),
            )
            print(json.dumps(repository.diagram_artwork().create_diagram(spec), indent=2, sort_keys=True))
            return 0

        if args.beyond_command == "artwork":
            spec_payload = json.loads(Path(args.spec).read_text())
            spec = ArtworkSpec(
                artwork_id=spec_payload["artwork_id"],
                title=spec_payload["title"],
                linguistic_description=spec_payload["linguistic_description"],
                visual_style=spec_payload.get("visual_style", ""),
                computational_definition=spec_payload.get("computational_definition", {}),
                section_id=spec_payload.get("section_id"),
            )
            print(json.dumps(repository.diagram_artwork().create_artwork(spec), indent=2, sort_keys=True))
            return 0

        print("Unknown beyond command")
        return 1

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Codynamic Book Machine - Multi-agent book authoring system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Bootstrap the system
  ./main.py bootstrap
  
  # Check system status
  ./main.py status
  
  # Validate an outline
  ./main.py validate outline.yaml
  
  # Show schema registry
  ./main.py registry

  # Start conversational intake for a new book
  ./main.py intake data/book_data/new_book init --title "Working Title"

  # Import an existing outline through the converter
  ./main.py import outline existing_outline.md

  # Create a proposal-first section draft
  ./main.py authoring data/book_data/my_book propose-section intro "Draft text"

  # Compile a canonical book or selected section
  ./main.py typeset data/book_data/my_book compile --section-id intro
        """
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # Bootstrap command
    bootstrap_parser = subparsers.add_parser(
        'bootstrap',
        help='Bootstrap the system and verify it is ready'
    )
    bootstrap_parser.set_defaults(func=cmd_bootstrap)
    
    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show current system status'
    )
    status_parser.set_defaults(func=cmd_status)
    
    # Validate command
    validate_parser = subparsers.add_parser(
        'validate',
        help='Validate an outline file'
    )
    validate_parser.add_argument(
        'outline',
        help='Path to outline YAML file'
    )
    validate_parser.add_argument(
        '--skip-bootstrap',
        action='store_true',
        help='Skip bootstrap phase (faster but may fail)'
    )
    validate_parser.set_defaults(func=cmd_validate_outline)
    
    # Registry command
    registry_parser = subparsers.add_parser(
        'registry',
        help='Show schema registry information'
    )
    registry_parser.add_argument(
        '--skip-bootstrap',
        action='store_true',
        help='Skip bootstrap phase'
    )
    registry_parser.set_defaults(func=cmd_registry)

    # Intake command
    intake_parser = subparsers.add_parser(
        'intake',
        help='Conversational zero-to-outline book intake'
    )
    intake_parser.add_argument(
        'book_root',
        help='Book root under data/book_data or another canonical book directory'
    )
    intake_subparsers = intake_parser.add_subparsers(
        dest='intake_command',
        help='Intake action to run',
        required=True,
    )

    intake_init = intake_subparsers.add_parser('init', help='Create a new intake-ready book')
    intake_init.add_argument('--title', help='Optional working title')
    intake_init.set_defaults(func=cmd_intake)

    intake_next = intake_subparsers.add_parser('next', help='Show the next Socratic prompt')
    intake_next.set_defaults(func=cmd_intake)

    intake_answer = intake_subparsers.add_parser('answer', help='Record an intake answer')
    intake_answer.add_argument('question_id', help='Question id from the intake prompt')
    intake_answer.add_argument('answer', help='Answer text to persist')
    intake_answer.set_defaults(func=cmd_intake)

    intake_plan = intake_subparsers.add_parser('plan', help='Generate the initial book plan')
    intake_plan.set_defaults(func=cmd_intake)

    # Import command
    import_parser = subparsers.add_parser(
        'import',
        help='Import external artifacts into canonical book projects'
    )
    import_subparsers = import_parser.add_subparsers(
        dest='import_command',
        help='Artifact type to import',
        required=True,
    )

    import_outline = import_subparsers.add_parser(
        'outline',
        help='Import an existing outline using the converter'
    )
    import_outline.add_argument('input', help='Path to outline file to import')
    import_outline.add_argument(
        '--book-root',
        help='Optional target book root. Defaults to data/book_data/<work_id>'
    )
    import_outline.add_argument(
        '--book-data-dir',
        default='data/book_data',
        help='Directory for imported books when --book-root is omitted'
    )
    import_outline.add_argument(
        '--use-llm',
        choices=['auto', 'always', 'never'],
        default='auto',
        help='Whether converter may use LLM fallback for unknown outline formats'
    )
    import_outline.add_argument(
        '--register',
        action='store_true',
        help='Register imported outline in the book library and make it active'
    )
    import_outline.set_defaults(func=cmd_import)

    # Authoring command
    authoring_parser = subparsers.add_parser(
        'authoring',
        help='Proposal-first authoring and review loop actions'
    )
    authoring_parser.add_argument(
        'book_root',
        nargs='?',
        help='Book root for authoring actions'
    )
    authoring_subparsers = authoring_parser.add_subparsers(
        dest='authoring_command',
        help='Authoring action to run',
        required=True,
    )

    propose_section = authoring_subparsers.add_parser('propose-section', help='Propose a section payload edit')
    propose_section.add_argument('section_id')
    propose_section.add_argument('content', nargs='?', default='')
    propose_section.add_argument('--content-file')
    propose_section.add_argument('--agent-id', default='section_agent')
    propose_section.add_argument('--rationale', default='Draft section payload.')
    propose_section.add_argument('--extension', default='.md')
    propose_section.add_argument('--mode', choices=['proposal', 'full-auto'], default='proposal')
    propose_section.set_defaults(func=cmd_authoring)

    accept_proposal = authoring_subparsers.add_parser('accept', help='Accept a proposal and write its file')
    accept_proposal.add_argument('proposal_id')
    accept_proposal.add_argument('--reviewer', default='user')
    accept_proposal.add_argument('--note', default='')
    accept_proposal.set_defaults(func=cmd_authoring)

    reject_proposal = authoring_subparsers.add_parser('reject', help='Reject a proposal')
    reject_proposal.add_argument('proposal_id')
    reject_proposal.add_argument('--reviewer', default='user')
    reject_proposal.add_argument('--note', default='')
    reject_proposal.set_defaults(func=cmd_authoring)

    media_request = authoring_subparsers.add_parser('media-request', help='Request media from the diagram agent')
    media_request.add_argument('section_id')
    media_request.add_argument('description')
    media_request.add_argument('--requesting-agent', default='section_agent')
    media_request.add_argument('--media-type', default='tikz')
    media_request.set_defaults(func=cmd_authoring)

    media_fulfill = authoring_subparsers.add_parser('media-fulfill', help='Fulfill a media request')
    media_fulfill.add_argument('request_id')
    media_fulfill.add_argument('content', nargs='?', default='')
    media_fulfill.add_argument('--content-file')
    media_fulfill.add_argument('--diagram-agent', default='diagram_agent')
    media_fulfill.add_argument('--extension', default='.tikz')
    media_fulfill.set_defaults(func=cmd_authoring)

    check = authoring_subparsers.add_parser('check', help='Record a gardener section check')
    check.add_argument('section_id')
    check.add_argument('--intent', choices=['pass', 'warn', 'fail'], default='pass')
    check.add_argument('--dependencies', choices=['pass', 'warn', 'fail'], default='pass')
    check.add_argument('--claim-clarity', choices=['pass', 'warn', 'fail'], default='pass')
    check.add_argument('--latex', choices=['pass', 'warn', 'fail'], default='pass')
    check.add_argument('--rationale', default='')
    check.set_defaults(func=cmd_authoring)

    memory = authoring_subparsers.add_parser('memory', help='Build communication log memory')
    memory.add_argument('--data-root', default='data')
    memory.set_defaults(func=cmd_authoring)

    # Typesetting command
    typeset_parser = subparsers.add_parser(
        'typeset',
        help='Document assembly, LaTeX compilation, styles, and exports'
    )
    typeset_parser.add_argument(
        'book_root',
        nargs='?',
        help='Book root for typesetting actions'
    )
    typeset_subparsers = typeset_parser.add_subparsers(
        dest='typeset_command',
        help='Typesetting action to run',
        required=True,
    )

    styles = typeset_subparsers.add_parser('styles', help='List available document styles')
    styles.set_defaults(func=cmd_typeset)

    set_style = typeset_subparsers.add_parser('set-style', help='Persist selected document style in the book object')
    set_style.add_argument('style_id')
    set_style.set_defaults(func=cmd_typeset)

    assemble = typeset_subparsers.add_parser('assemble', help='Assemble book or section TeX without compiling')
    assemble.add_argument('--section-id')
    assemble.add_argument('--output')
    assemble.set_defaults(func=cmd_typeset)

    compile_cmd = typeset_subparsers.add_parser('compile', help='Compile book or section TeX to PDF')
    compile_cmd.add_argument('--section-id')
    compile_cmd.add_argument('--engine')
    compile_cmd.set_defaults(func=cmd_typeset)

    export_html = typeset_subparsers.add_parser('export-html', help='Export canonical content to HTML')
    export_html.set_defaults(func=cmd_typeset)

    # Desktop app JSON API
    app_parser = subparsers.add_parser(
        'app',
        help='Internal desktop app JSON API'
    )
    app_parser.add_argument(
        '--book-root',
        default=None,
        help='Book root to load'
    )
    app_parser.add_argument(
        '--book-id',
        default=None,
        help='Book id from the library registry'
    )
    app_parser.add_argument(
        '--book-data-dir',
        default='data/book_data',
        help='Book library data directory'
    )
    app_parser.add_argument(
        '--data-root',
        default='data',
        help='Application data root'
    )
    app_subparsers = app_parser.add_subparsers(
        dest='app_command',
        help='App API action',
        required=True,
    )

    app_state = app_subparsers.add_parser('state', help='Return full UI state')
    app_state.add_argument('--selected-id')
    app_state.set_defaults(func=cmd_app)

    app_section = app_subparsers.add_parser('section', help='Return one section payload')
    app_section.add_argument('section_id')
    app_section.set_defaults(func=cmd_app)

    app_save = app_subparsers.add_parser('save-section', help='Save one section payload')
    app_save.add_argument('section_id')
    app_save.add_argument('--content-file', required=True)
    app_save.set_defaults(func=cmd_app)

    app_compile = app_subparsers.add_parser('compile-section', help='Compile one section and return compile result')
    app_compile.add_argument('section_id')
    app_compile.set_defaults(func=cmd_app)

    app_compile_book = app_subparsers.add_parser('compile-book', help='Compile the full book and return compile result')
    app_compile_book.set_defaults(func=cmd_app)

    app_review = app_subparsers.add_parser('request-review', help='Record a full-review request')
    app_review.add_argument('--subject', default='book')
    app_review.set_defaults(func=cmd_app)

    app_create_section = app_subparsers.add_parser('create-section', help='Create a section under a chapter')
    app_create_section.add_argument('title')
    app_create_section.add_argument('--parent-id')
    app_create_section.set_defaults(func=cmd_app)

    app_create_chapter = app_subparsers.add_parser('create-chapter', help='Create a top-level chapter')
    app_create_chapter.add_argument('title')
    app_create_chapter.set_defaults(func=cmd_app)

    app_update_outline_node = app_subparsers.add_parser('update-outline-node', help='Rename an outline node')
    app_update_outline_node.add_argument('node_id')
    app_update_outline_node.add_argument('title')
    app_update_outline_node.set_defaults(func=cmd_app)

    app_accept_proposal = app_subparsers.add_parser('accept-proposal', help='Accept an edit proposal')
    app_accept_proposal.add_argument('proposal_id')
    app_accept_proposal.add_argument('--note', default='')
    app_accept_proposal.set_defaults(func=cmd_app)

    app_reject_proposal = app_subparsers.add_parser('reject-proposal', help='Reject an edit proposal')
    app_reject_proposal.add_argument('proposal_id')
    app_reject_proposal.add_argument('--note', default='')
    app_reject_proposal.set_defaults(func=cmd_app)

    app_revise_proposal = app_subparsers.add_parser('revise-proposal', help='Revise an edit proposal')
    app_revise_proposal.add_argument('proposal_id')
    app_revise_proposal.add_argument('--content-file', required=True)
    app_revise_proposal.add_argument('--note', default='')
    app_revise_proposal.set_defaults(func=cmd_app)

    app_library = app_subparsers.add_parser('library', help='Return registered books and active book')
    app_library.set_defaults(func=cmd_app)

    app_open = app_subparsers.add_parser('open-book', help='Set active book')
    app_open.add_argument('book_id')
    app_open.set_defaults(func=cmd_app)

    app_new = app_subparsers.add_parser('new-book', help='Create a new intake-ready book')
    app_new.add_argument('title')
    app_new.add_argument('--book-id')
    app_new.add_argument('--tags', default='')
    app_new.set_defaults(func=cmd_app)

    app_archive = app_subparsers.add_parser('archive-book', help='Archive a registered book')
    app_archive.add_argument('book_id')
    app_archive.set_defaults(func=cmd_app)

    # Beyond-MVP command
    beyond_parser = subparsers.add_parser(
        'beyond',
        help='Beyond-MVP diagrams, knowledge graph, and changesets'
    )
    beyond_parser.add_argument(
        '--book-root',
        default='data/book_data/codynamic_theory_book',
        help='Book root to use'
    )
    beyond_subparsers = beyond_parser.add_subparsers(
        dest='beyond_command',
        help='Beyond-MVP action',
        required=True,
    )

    beyond_graph = beyond_subparsers.add_parser('graph', help='Analyze citation, dependency, and concept graphs')
    beyond_graph.set_defaults(func=cmd_beyond)

    beyond_diagram = beyond_subparsers.add_parser('diagram', help='Create a structured diagram from a JSON spec')
    beyond_diagram.add_argument('spec')
    beyond_diagram.set_defaults(func=cmd_beyond)

    beyond_artwork = beyond_subparsers.add_parser('artwork', help='Create a structured artwork spec from JSON')
    beyond_artwork.add_argument('spec')
    beyond_artwork.set_defaults(func=cmd_beyond)

    beyond_changeset = beyond_subparsers.add_parser('changeset', help='Create a git-backed proposal bundle')
    beyond_changeset.add_argument('title')
    beyond_changeset.add_argument('--agent-id', default='agent')
    beyond_changeset.add_argument('--branch-name')
    beyond_changeset.add_argument('files', nargs='*')
    beyond_changeset.set_defaults(func=cmd_beyond)
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Run command
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())

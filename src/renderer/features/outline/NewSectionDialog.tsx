import { type FormEvent, useState } from "react";

interface NewSectionDialogProps {
  parentTitle?: string;
  onCreate: (title: string) => Promise<void>;
  onCancel: () => void;
}

export function NewSectionDialog({ parentTitle, onCreate, onCancel }: NewSectionDialogProps) {
  const [title, setTitle] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) {
      return;
    }
    setIsSaving(true);
    try {
      await onCreate(title.trim());
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="inline-dialog" role="dialog" aria-label="Create section">
      <form onSubmit={submit}>
        <p className="eyebrow">New section {parentTitle ? `in ${parentTitle}` : ""}</p>
        <input autoFocus value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Section title" />
        <div className="dialog-actions">
          <button className="secondary-action" type="button" onClick={onCancel}>Cancel</button>
          <button className="primary-action" type="submit" disabled={isSaving || !title.trim()}>
            {isSaving ? "Creating" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}

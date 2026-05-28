import { useState } from "react";
import type { EditProposal } from "../../api/types";

interface ProposalReviewPanelProps {
  proposals: EditProposal[];
  onReview: (proposalId: string, action: "accept" | "reject") => Promise<void>;
  onRevise: (proposalId: string, content: string) => Promise<void>;
}

export function ProposalReviewPanel({ proposals, onReview, onRevise }: ProposalReviewPanelProps) {
  const pending = proposals.filter((proposal) => proposal.status === "pending");
  const [revisionId, setRevisionId] = useState<string | null>(null);
  const [revisionContent, setRevisionContent] = useState("");

  return (
    <div className="proposal-review">
      <div className="detail-section-title">
        <p className="eyebrow">Proposal Review</p>
        <h3>{pending.length} pending</h3>
      </div>
      {proposals.length === 0 ? <p className="empty-state">No agent proposals have been created for this book yet.</p> : null}
      {proposals.slice().reverse().slice(0, 8).map((proposal) => (
        <article className={`proposal-item ${proposal.status}`} key={proposal.proposal_id}>
          <div className="proposal-heading">
            <div>
              <strong>{proposal.target_path}</strong>
              <span>{proposal.agent_id} · {proposal.status}</span>
            </div>
          </div>
          <p>{proposal.rationale || "No rationale supplied."}</p>
          <pre>{proposal.diff?.slice(0, 1200) || "No textual diff available."}</pre>
          {revisionId === proposal.proposal_id ? (
            <div className="proposal-revision">
              <textarea
                value={revisionContent}
                onChange={(event) => setRevisionContent(event.target.value)}
                rows={8}
                aria-label="Revised proposal content"
              />
              <div className="proposal-actions">
                <button className="secondary-action" type="button" onClick={() => setRevisionId(null)}>Cancel</button>
                <button
                  className="primary-action"
                  type="button"
                  onClick={async () => {
                    await onRevise(proposal.proposal_id, revisionContent);
                    setRevisionId(null);
                    setRevisionContent("");
                  }}
                >
                  Save Revision
                </button>
              </div>
            </div>
          ) : null}
          {proposal.status === "pending" ? (
            <div className="proposal-actions">
              <button className="primary-action" type="button" onClick={() => onReview(proposal.proposal_id, "accept")}>Accept</button>
              <button className="secondary-action" type="button" onClick={() => onReview(proposal.proposal_id, "reject")}>Reject</button>
              <button
                className="secondary-action"
                type="button"
                onClick={() => {
                  setRevisionId(proposal.proposal_id);
                  setRevisionContent(proposal.proposed_content ?? "");
                }}
              >
                Revise
              </button>
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

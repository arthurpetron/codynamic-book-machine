import type { EditProposal } from "../../api/types";

interface ProposalReviewPanelProps {
  proposals: EditProposal[];
  onReview: (proposalId: string, action: "accept" | "reject") => Promise<void>;
}

export function ProposalReviewPanel({ proposals, onReview }: ProposalReviewPanelProps) {
  const pending = proposals.filter((proposal) => proposal.status === "pending");

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
          {proposal.status === "pending" ? (
            <div className="proposal-actions">
              <button className="primary-action" type="button" onClick={() => onReview(proposal.proposal_id, "accept")}>Accept</button>
              <button className="secondary-action" type="button" onClick={() => onReview(proposal.proposal_id, "reject")}>Reject</button>
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

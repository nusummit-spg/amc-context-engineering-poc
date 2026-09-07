import { MessageSquareText } from "lucide-react";
import ModalCard from "./ModalCard";
import FeedbackContainer from "../../components/feedback/FeedbackContainer";

export default function FeedbackModal({ open, onClose, data }) {
  return (
    <ModalCard
      open={open}
      onClose={onClose}
      title="Response Feedback"
      icon={<MessageSquareText size={15} strokeWidth={1.75} />}
      query={data?.query}
      size="md"
    >
      {data && (
        <FeedbackContainer
          responseId={data.responseId}
          interactionId={data.interactionId}
          sessionId={data.sessionId}
          turnNumber={data.turnNumber}
          query={data.query}
          actorId={data.actorId}
          actorRole={data.actorRole}
          isCurrentTurn={data.isCurrentTurn}
        />
      )}
    </ModalCard>
  );
}

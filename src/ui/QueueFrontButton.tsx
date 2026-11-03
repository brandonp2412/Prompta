import { useState } from "react";
import { localPost, localRejectionDetail } from "./localMutation";
import { notify } from "./toast";

type Props = {
  endpoint: string;
  label: string;
  onMoved: () => Promise<void>;
};

export default function QueueFrontButton({ endpoint, label, onMoved }: Props) {
  const [moving, setMoving] = useState(false);
  async function move() {
    if (moving) return;
    setMoving(true);
    try {
      const response = await localPost(endpoint, {});
      if (!response.ok)
        throw new Error(await localRejectionDetail(response, "Could not move this item."));
      notify("Moved to the front of the queue.", "success");
    } catch (error) {
      notify(error instanceof Error ? error.message : "Could not move this item.", "error");
    } finally {
      await onMoved();
      setMoving(false);
    }
  }
  return (
    <button
      type="button"
      className="row-action queue-front chat-action-button"
      title="Run next when a slot is free; retry delays still apply"
      aria-label={"Bump " + label + " to front of queue"}
      disabled={moving}
      onClick={() => void move()}
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M5 4h14M12 20V9m-5 5 5-5 5 5" />
      </svg>
      {moving ? "Moving…" : "Bump to front"}
    </button>
  );
}

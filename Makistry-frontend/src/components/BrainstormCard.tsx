import { BrainstormResp } from "@/hooks/useBrainstorm";

export default function BrainstormCard({ data }: { data: BrainstormResp }) {
  const b = data.brainstorm;
  return (
    <article className="rounded-lg border p-4 shadow">
      <h2 className="text-xl font-semibold">Design One-Liner</h2>
      <p className="italic">{b.design_one_liner}</p>

      <h3 className="mt-4 font-medium">Key Features</h3>
      <ul className="list-disc pl-6">
        {b.key_features?.map((f) => (
          <li key={f}>{f}</li>
        ))}
      </ul>
    </article>
  );
}

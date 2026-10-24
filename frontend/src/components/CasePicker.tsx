import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";
import { api } from "@/api";
import { cn } from "@/lib/utils";

export function CasePicker() {
  const cases = useQuery({ queryKey: ["cases"], queryFn: () => api.listCases() });
  if (cases.isPending) return <p className="text-stone-500">Loading cases…</p>;
  if (cases.isError) return <p className="text-red-700">The cases could not be loaded.</p>;
  return (
    <nav aria-label="Cases">
      <ul className="flex flex-col gap-2">
        {cases.data.map((c) => (
          <li key={c.id}>
            <Link
              to={`/?case=${c.id}`}
              className={cn(
                "block rounded-md border border-stone-300 bg-white p-3 hover:border-stone-500",
                "focus-visible:ring-2 focus-visible:ring-stone-500 focus-visible:outline-none",
              )}
            >
              <span className="block font-semibold">{c.title}</span>
              <span className="mt-1 block text-sm text-stone-600">{c.summary}</span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

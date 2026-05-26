import { useQuery } from "@tanstack/react-query";
import { getHealthz } from "../client";

// Reference pattern: every backend route gets a thin TanStack Query wrapper
// here that calls into the generated SDK in src/client/. Components consume
// these hooks — they never import from src/client/ directly.
export function useHealth() {
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const res = await getHealthz();
      return res.data;
    },
  });
}

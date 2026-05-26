import { Routes, Route } from "react-router-dom";
import { useHealth } from "./api/health";

function Home() {
  const { data, isLoading, isError } = useHealth();
  return (
    <main className="min-h-screen p-8 font-sans">
      <h1 className="text-2xl font-semibold">POC boilerplate</h1>
      <p className="mt-2 text-sm text-gray-600">
        Backend health:{" "}
        {isLoading
          ? "checking…"
          : isError
            ? "unreachable"
            : (data?.status ?? "unknown")}
      </p>
    </main>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Home />} />
    </Routes>
  );
}

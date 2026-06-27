import { Routes, Route } from "react-router-dom";

export default function App() {
  return (
    <Routes>
      <Route
        path="/"
        element={
          <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50">
            <div className="text-center">
              <h1 className="text-4xl font-bold text-brand-700">AI FinOps</h1>
              <p className="mt-4 text-lg text-gray-600">
                AI cost observability and financial operations platform
              </p>
              <p className="mt-2 text-sm text-gray-400">Application coming soon</p>
            </div>
          </div>
        }
      />
    </Routes>
  );
}

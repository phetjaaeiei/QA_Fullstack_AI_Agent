import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Dashboard from "./pages/Dashboard";

function isAuthenticated() {
  return !!localStorage.getItem("access_token");
}

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  return isAuthenticated() ? <>{children}</> : <Navigate to="/login" replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<LoginPage />} />
      </Routes>
    </BrowserRouter>
  );
}

function LoginPage() {
  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = e.currentTarget;
    const email = (form.elements.namedItem("email") as HTMLInputElement).value;
    const password = (form.elements.namedItem("password") as HTMLInputElement).value;
    const { login } = await import("./lib/api");
    await login(email, password);
    window.location.href = "/";
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50">
      <form onSubmit={handleSubmit} className="bg-white p-8 rounded-lg shadow-md w-96 space-y-4">
        <h1 className="text-2xl font-bold text-slate-800">QA Brain</h1>
        <p className="text-slate-500 text-sm">AI-Powered QA Platform</p>
        <input name="email" type="email" placeholder="Email" required className="w-full border rounded px-3 py-2 text-sm" />
        <input name="password" type="password" placeholder="Password" required className="w-full border rounded px-3 py-2 text-sm" />
        <button type="submit" className="w-full bg-slate-800 text-white rounded px-3 py-2 text-sm font-medium hover:bg-slate-700">
          Sign In
        </button>
      </form>
    </div>
  );
}

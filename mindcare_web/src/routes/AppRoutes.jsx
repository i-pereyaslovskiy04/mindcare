import { Routes, Route, Navigate } from "react-router-dom";
import { useSelector } from "react-redux";
import Login from "../features/auth/Login";
import Home from "../pages/Home/Home";
import Landing from "../pages/Landing/Landing";
import NotFound from "../pages/NotFound/NotFound";

function RequireAuth({ children }) {
  const { user } = useSelector((s) => s.auth);
  return user ? children : <Navigate to="/login" replace />;
}

function GuestOnly({ children }) {
  const { user } = useSelector((s) => s.auth);
  return user ? <Navigate to="/dashboard" replace /> : children;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />

      <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />

      <Route path="/dashboard" element={<RequireAuth><Home /></RequireAuth>} />
      <Route path="/psychologist" element={<RequireAuth><Home /></RequireAuth>} />
      <Route path="/admin" element={<RequireAuth><Home /></RequireAuth>} />

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}

import { Navigate, Route, Routes } from "react-router-dom";
import RequireAuth from "./RequireAuth";
import Admin from "./pages/Admin";
import Home from "./pages/Home";
import Login from "./pages/Login";
import MfaSetup from "./pages/MfaSetup";
import Register from "./pages/Register";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route element={<RequireAuth />}>
        <Route path="/" element={<Home />} />
        <Route path="/admin" element={<Admin />} />
        <Route path="/mfa/setup" element={<MfaSetup />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

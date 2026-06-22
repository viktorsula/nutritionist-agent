import { Navigate, Route, Routes } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "./auth/AuthProvider";
import { ProtectedRoute } from "./routes/ProtectedRoute";
import { Login } from "./pages/Login";
import { AccessRestricted } from "./pages/AccessRestricted";
import { ClientArea } from "./pages/client/ClientArea";
import { NutritionistShell } from "./pages/nutritionist/NutritionistShell";
import { Header } from "./components/Header";

/** Корень: ведёт авторизованного на его кабинет, иначе на вход. */
function RootRedirect() {
  const { session, appUser, loading } = useAuth();
  const { t } = useTranslation();
  if (loading) return <div className="p-8 text-gray-500">{t("loading")}</div>;
  if (!session || !appUser) return <Navigate to="/login" replace />;
  return <Navigate to={`/${appUser.role}`} replace />;
}

/** /login: если уже вошёл — не показываем форму. */
function LoginRoute() {
  const { session, appUser, loading } = useAuth();
  if (loading) return null;
  if (session && appUser) return <Navigate to={`/${appUser.role}`} replace />;
  return <Login />;
}

/** Observer в v1.0 отключён — показываем уведомление. */
function ObserverNotice() {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <div className="mx-auto mt-20 max-w-md rounded-xl bg-white p-8 text-center shadow">
        <div className="mb-3 text-3xl">👁️</div>
        <p className="text-sm text-gray-500">
          Роль «Наблюдатель» доступна в продакшн-версии (v2.0).
        </p>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<RootRedirect />} />
      <Route path="/login" element={<LoginRoute />} />
      <Route path="/access-restricted" element={<AccessRestricted />} />
      <Route
        path="/client"
        element={
          <ProtectedRoute allow={["client"]}>
            <ClientArea />
          </ProtectedRoute>
        }
      />
      <Route
        path="/nutritionist"
        element={
          <ProtectedRoute allow={["nutritionist"]}>
            <NutritionistShell />
          </ProtectedRoute>
        }
      />
      <Route
        path="/observer"
        element={
          <ProtectedRoute allow={["observer"]}>
            <ObserverNotice />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

import { useTranslation } from "react-i18next";
import { Header } from "../components/Header";
import { useAuth } from "../auth/AuthProvider";

export function AccessRestricted() {
  const { t } = useTranslation();
  const { appUser } = useAuth();
  return (
    <div className="min-h-screen bg-gray-50">
      <Header />
      <div className="mx-auto mt-20 max-w-md rounded-xl bg-white p-8 text-center shadow">
        <div className="mb-3 text-3xl">🔒</div>
        <h1 className="mb-2 text-lg font-semibold text-gray-800">
          {t("access_restricted.title")}
        </h1>
        <p className="text-sm text-gray-500">
          {appUser?.web_message || t("access_restricted.body")}
        </p>
      </div>
    </div>
  );
}

import { useEffect } from "react";
import { BrowserRouter } from "react-router-dom";
import { Provider, useDispatch } from "react-redux";
import { store } from "./store/store";
import { fetchMe } from "./store/authSlice";
import AppRoutes from "./routes/AppRoutes";
import "./styles/global.css";

function AppInner() {
  const dispatch = useDispatch();

  useEffect(() => {
    if (localStorage.getItem("token")) dispatch(fetchMe());
  }, [dispatch]);

  return <AppRoutes />;
}

export default function App() {
  return (
    <Provider store={store}>
      <BrowserRouter>
        <AppInner />
      </BrowserRouter>
    </Provider>
  );
}

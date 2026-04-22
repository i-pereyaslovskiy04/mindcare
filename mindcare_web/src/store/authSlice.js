import { createSlice, createAsyncThunk } from "@reduxjs/toolkit";
import api from "../api/api";

export const login = createAsyncThunk("auth/login", async (credentials, { rejectWithValue }) => {
  try {
    const { data } = await api.post("/auth/login", credentials);
    localStorage.setItem("token", data.access_token);
    return data.user;
  } catch (err) {
    return rejectWithValue(err.response?.data?.detail || "Ошибка входа");
  }
});

export const register = createAsyncThunk("auth/register", async (body, { rejectWithValue }) => {
  try {
    const { data } = await api.post("/auth/register", body);
    localStorage.setItem("token", data.access_token);
    return data.user;
  } catch (err) {
    return rejectWithValue(err.response?.data?.detail || "Ошибка регистрации");
  }
});

export const fetchMe = createAsyncThunk("auth/me", async (_, { rejectWithValue }) => {
  try {
    const { data } = await api.get("/auth/me");
    return data;
  } catch {
    return rejectWithValue(null);
  }
});

const authSlice = createSlice({
  name: "auth",
  initialState: { user: null, loading: false, error: null },
  reducers: {
    logout(state) {
      state.user = null;
      localStorage.removeItem("token");
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(login.pending, (state) => { state.loading = true; state.error = null; })
      .addCase(login.fulfilled, (state, { payload }) => { state.loading = false; state.user = payload; })
      .addCase(login.rejected, (state, { payload }) => { state.loading = false; state.error = payload; })
      .addCase(register.pending, (state) => { state.loading = true; state.error = null; })
      .addCase(register.fulfilled, (state, { payload }) => { state.loading = false; state.user = payload; })
      .addCase(register.rejected, (state, { payload }) => { state.loading = false; state.error = payload; })
      .addCase(fetchMe.fulfilled, (state, { payload }) => { state.user = payload; })
      .addCase(fetchMe.rejected, (state) => { state.user = null; });
  },
});

export const { logout } = authSlice.actions;
export default authSlice.reducer;

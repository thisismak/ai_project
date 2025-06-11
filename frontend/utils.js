async function apiRequest(url, method, data) {
  const token = localStorage.getItem('token');
  const headers = {
    'Content-Type': 'application/json',
    ...(token && { Authorization: `Bearer ${token}` }),
  };
  console.log('API Request:', { url, method, headers, data });
  try {
    const response = await fetch(url, {
      method,
      headers,
      ...(data && method !== 'GET' && { body: JSON.stringify(data) }),
    });
    const responseData = await response.json();
    console.log('API Response:', { status: response.status, data: responseData });
    if (response.status === 403) {
      console.warn('無效令牌，跳轉到登錄頁面');
      localStorage.removeItem('token');
      window.location.href = 'login.html';
    }
    if (!response.ok) {
      throw new Error(responseData.error || `HTTP ${response.status}: ${response.statusText}`);
    }
    return responseData;
  } catch (error) {
    console.error('API 請求失敗:', { url, method, error: error.message, stack: error.stack });
    throw error;
  }
}
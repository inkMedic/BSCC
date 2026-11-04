// Released under the MIT License. See LICENSE for details.
// Community Plus. HTTPS/WSS business logic lives in baplus; no official library.
#include <Python.h>
#include <mutex>
#include <atomic>
#if BA_PLATFORM_ANDROID
#include <jni.h>
#include <SDL3/SDL.h>
extern "C" jclass BallisticaCommunityActivity();
#endif
#include "ballistica/base/base.h"
#include "ballistica/base/support/plus_soft.h"
#include "ballistica/base/support/classic_soft.h"
#include "ballistica/shared/foundation/exception.h"
namespace ballistica::base {
namespace {
std::mutex identity_lock;
std::string account_id;
std::atomic<bool> party_dirty{true};
auto SetIdentity(PyObject*, PyObject* args) -> PyObject* {
  const char* uid;
  const char* display_name;
  if (!PyArg_ParseTuple(args, "ss", &uid, &display_name)) return nullptr;
  std::scoped_lock lock(identity_lock);
  account_id = uid;
  if (auto* classic = BaseFeatureSet::Import()->classic()) {
    classic->V2SetV1AccountState(account_id.empty() ? "signed_out" : "signed_in",
                               uid, display_name);
  }
  Py_RETURN_NONE;
}
auto SetInstance(PyObject*, PyObject* args) -> PyObject* {
  const char* iid;
  double expiry;
  if (!PyArg_ParseTuple(args, "sd", &iid, &expiry)) return nullptr;
  BaseFeatureSet::Import()->SetGlobalAppInstanceUUID(iid, expiry);
  Py_RETURN_NONE;
}
auto PartyDirty(PyObject*, PyObject*) -> PyObject* {
  return PyBool_FromLong(party_dirty.exchange(false));
}
auto PartyState(PyObject*, PyObject*) -> PyObject* {
  try {
    if (auto* classic = BaseFeatureSet::Import()->classic()) {
      return classic->BuildPublicPartyStateVal();
    }
    Py_RETURN_NONE;
  } catch (const std::exception& exc) {
    PyErr_SetString(PyExc_RuntimeError, exc.what());
    return nullptr;
  }
}
auto SecureRefresh(PyObject*, PyObject* args) -> PyObject* {
  const char* value = nullptr;
  if (!PyArg_ParseTuple(args, "|z", &value)) return nullptr;
#if BA_PLATFORM_ANDROID
  auto* env = static_cast<JNIEnv*>(SDL_GetAndroidJNIEnv());
  auto cls = BallisticaCommunityActivity();
  jstring result;
  if (PyTuple_Size(args)) {
    auto method = env->GetStaticMethodID(cls, "storeRefresh", "(Ljava/lang/String;)V");
    auto text = value ? env->NewStringUTF(value) : nullptr;
    env->CallStaticVoidMethod(cls, method, text);
    if (text) env->DeleteLocalRef(text);
    result = nullptr;
  } else {
    auto method = env->GetStaticMethodID(cls, "loadRefresh", "()Ljava/lang/String;");
    result = static_cast<jstring>(env->CallStaticObjectMethod(cls, method));
  }
  if (env->ExceptionCheck()) {
    env->ExceptionClear();
    PyErr_SetString(PyExc_RuntimeError, "Android Keystore operation failed");
    return nullptr;
  }
  if (!result) Py_RETURN_NONE;
  const char* text = env->GetStringUTFChars(result, nullptr);
  auto* out = PyUnicode_FromString(text);
  env->ReleaseStringUTFChars(result, text);
  env->DeleteLocalRef(result);
  return out;
#else
  PyErr_SetString(PyExc_RuntimeError, "Secure refresh persistence requires Android Keystore");
  return nullptr;
#endif
}
PyMethodDef methods[] = {
  {"set_identity", SetIdentity, METH_VARARGS, nullptr},
  {"set_instance", SetInstance, METH_VARARGS, nullptr},
  {"party_dirty", PartyDirty, METH_NOARGS, nullptr},
  {"party_state", PartyState, METH_NOARGS, nullptr},
  {"secure_refresh", SecureRefresh, METH_VARARGS, nullptr},
  {nullptr, nullptr, 0, nullptr}
};
}  // namespace
class CommunityPlus final : public PlusSoftInterface {
 public:
  void OnAppStart() override {}
  void OnAppSuspend() override {}
  void OnAppUnsuspend() override {}
  void OnAppShutdown() override {}
  void OnAppShutdownComplete() override {}
  void ApplyAppConfig() override {}
  void OnScreenSizeChange() override {}
  void StepDisplayTime() override {}
  auto IsUnmodifiedBlessedBuild() -> bool override { return false; }
  auto HasBlessingHash() -> bool override { return false; }
  void AAT() override {}
  void AATE() override {}
  auto GAHU() -> std::optional<std::string> override { return {}; }
  void V1LoginDidChange() override {}
  void SetAdCompletionCall(PyObject*, bool) override { throw Exception("Community ads unavailable"); }
  void PushAdViewComplete(const std::string&, bool) override {}
  // Local party-size changes reach this even when publication is disabled.
  // Publication is intentionally unavailable; nothing is sent to a master.
  void PushPublicPartyState() override { party_dirty.store(true); }
  void DispatchRemoteAchievementList(const std::set<std::string>&) override {}
  void SetProductPrice(const std::string&, const std::string&) override {}
  void PushAnalyticsCall(const std::string&, int) override {}
  void PushPurchaseTransactionCall(const std::string&, const std::string&,
      const std::string&, const std::string&, bool) override {
    throw Exception("Community purchases unavailable");
  }
  auto GetAccountID() -> std::string override {
    std::scoped_lock lock(identity_lock);
    return account_id;
  }
  void ClientInfoQuery(const std::string&, const std::string&, const std::string&, int) override {
    throw Exception("Community room authentication has not been implemented");
  }
  auto CalcV1PeerHash(const std::string&) -> std::string override {
    throw Exception("Community room credentials have not been implemented");
  }
  void V1SetClientInfo(JsonObjBuilder*) override {
    throw Exception("Community handshake has not been implemented");
  }
  void DoPushSubmitAnalyticsCountsCall(const std::string&) override {}
  void SetHaveIncentivizedAd(bool) override {}
  auto HaveIncentivizedAd() -> bool override { return false; }
};
}  // namespace ballistica::base

extern "C" PyObject* DoPyInit__baplus() {
  static PyModuleDef def = {PyModuleDef_HEAD_INIT, "_baplus",
      "Community Plus; no official Plus binary.", -1, ballistica::base::methods};
  auto* module = PyModule_Create(&def);
  if (!module) return nullptr;
  static ballistica::base::CommunityPlus offline;
  ballistica::base::BaseFeatureSet::Import()->SetPlus(&offline);
  return module;
}

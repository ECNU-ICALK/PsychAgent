import { Menu, X } from "lucide-react";
import { ChatInput } from "./components/chat/ChatInput";
import { ChatMessages } from "./components/chat/ChatMessages";
import { FeedbackBanner } from "./components/common/FeedbackBanner";
import { StatusPill } from "./components/common/StatusPill";
import { HeaderBar } from "./components/layout/HeaderBar";
import { MobileBottomSheet } from "./components/layout/MobileBottomSheet";
import { RightPanel } from "./components/layout/RightPanel";
import { Sidebar } from "./components/layout/Sidebar";
import { VisitTimeline } from "./components/layout/VisitTimeline";
import { AuthModal } from "./components/modals/AuthModal";
import { CompleteCourseModal } from "./components/modals/CompleteCourseModal";
import { CreateCourseModal } from "./components/modals/CreateCourseModal";
import { SchoolModal } from "./components/modals/SchoolModal";
import { getCourseStatusText, getVisitStatusText } from "./components/common/statusText";
import { getSchoolDisplayName } from "./components/common/schoolText";
import { useMindCareApp } from "./hooks/useMindCareApp";

function getCourseTone(status) {
  if (status === "active") return "active";
  if (status === "completed") return "success";
  if (status === "archived") return "neutral";
  return "warning";
}

function getVisitTone(status) {
  if (status === "open") return "active";
  if (status === "closed") return "neutral";
  return "warning";
}

export default function App() {
  const app = useMindCareApp();

  return (
    <div className="flex h-screen w-full bg-white font-sans text-slate-900 selection:bg-teal-100">
      <button
        type="button"
        className="fixed left-4 top-4 z-40 rounded-lg border border-slate-200 bg-white p-2 shadow-md md:hidden"
        onClick={() => app.setSidebarOpen(!app.sidebarOpen)}
      >
        {app.sidebarOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
      </button>

      <Sidebar
        sidebarOpen={app.sidebarOpen}
        sidebarCollapsed={app.sidebarCollapsed}
        onClose={() => app.setSidebarOpen(false)}
        onToggleCollapse={() => app.setSidebarCollapsed(!app.sidebarCollapsed)}
        currentSchool={app.currentSchool}
        currentCourse={app.currentCourse}
        courses={app.courses}
        onSelectCourse={app.selectCourse}
        onOpenSchoolModal={() => app.setShowSchoolModal(true)}
        onOpenAuthModal={() => app.setShowAuthModal(true)}
        user={app.user}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <HeaderBar
          currentSchool={app.currentSchool}
          currentCourse={app.currentCourse}
          currentVisit={app.currentVisit}
          selectedSchoolId={app.selectedSchoolId}
          token={app.token}
          canCreateCourse={app.canCreateCourse}
          canStartNextVisit={app.canStartNextVisit}
          canCompleteCourse={app.canCompleteCourse}
          onOpenCreateCourseModal={() => app.setShowCreateCourseModal(true)}
          onStartNextVisit={app.startNextVisit}
          onContinueVisit={app.continueCurrentVisit}
          onCloseVisit={app.closeCurrentVisit}
          onOpenCompleteCourseModal={() => app.setShowCompleteCourseModal(true)}
        />

        <FeedbackBanner feedback={app.feedback} onClose={app.clearFeedback} />

        <div className="flex min-h-0 flex-1">
          <VisitTimeline
            currentCourse={app.currentCourse}
            visits={app.visits}
            currentVisit={app.currentVisit}
            canStartNextVisit={app.canStartNextVisit}
            onStartNextVisit={app.startNextVisit}
            onSelectVisit={app.selectVisit}
          />

          <main className="flex min-w-0 flex-1 flex-col">
            <div className="border-b border-slate-200 bg-white px-4 py-3 sm:px-6">
              {app.currentCourse ? (
                <div className="flex flex-wrap items-center gap-2 text-xs text-slate-700">
                  <span className="rounded-md bg-slate-100 px-2 py-1">
                    流派：{getSchoolDisplayName(app.currentSchool)}
                  </span>
                  <span className="rounded-md bg-slate-100 px-2 py-1">
                    疗程：{app.currentCourse.title || "未命名疗程"}
                  </span>
                  <span className="rounded-md bg-slate-100 px-2 py-1">
                    会谈：{app.currentVisit ? `第 ${app.currentVisit.visit_no} 次` : "尚未开始"}
                  </span>
                  <StatusPill
                    text={getCourseStatusText(app.currentCourse.status)}
                    tone={getCourseTone(app.currentCourse.status)}
                  />
                  {app.currentVisit ? (
                    <StatusPill
                      text={getVisitStatusText(app.currentVisit.status)}
                      tone={getVisitTone(app.currentVisit.status)}
                    />
                  ) : null}
                </div>
                ) : (
                  <p className="text-sm text-slate-600">
                    从“流派 -&gt; 疗程 -&gt; 会谈 -&gt; 消息”开始：先选择流派并创建疗程。
                  </p>
                )}
            </div>

            <ChatMessages
              currentCourse={app.currentCourse}
              currentVisit={app.currentVisit}
              currentSchool={app.currentSchool}
              isTyping={app.isTyping}
              chatEndRef={app.chatEndRef}
              hasToken={Boolean(app.token)}
            />

            <ChatInput
              currentCourse={app.currentCourse}
              currentVisit={app.currentVisit}
              input={app.input}
              isTyping={app.isTyping}
              onInputChange={app.setInput}
              onSend={app.sendMessage}
            />
          </main>

          <RightPanel currentCourse={app.currentCourse} currentVisit={app.currentVisit} />
        </div>
      </div>

      <MobileBottomSheet
        token={app.token}
        selectedSchoolId={app.selectedSchoolId}
        currentCourse={app.currentCourse}
        currentVisit={app.currentVisit}
        canCreateCourse={app.canCreateCourse}
        canStartNextVisit={app.canStartNextVisit}
        canCompleteCourse={app.canCompleteCourse}
        onOpenCreateCourseModal={() => app.setShowCreateCourseModal(true)}
        onStartNextVisit={app.startNextVisit}
        onContinueVisit={app.continueCurrentVisit}
        onCloseVisit={app.closeCurrentVisit}
        onOpenCompleteCourseModal={() => app.setShowCompleteCourseModal(true)}
      >
        <RightPanel currentCourse={app.currentCourse} currentVisit={app.currentVisit} embedded />
      </MobileBottomSheet>

      <AuthModal
        open={app.showAuthModal}
        user={app.user}
        authMode={app.authMode}
        authForm={app.authForm}
        onClose={() => app.setShowAuthModal(false)}
        onChangeMode={app.setAuthMode}
        onChangeForm={app.setAuthForm}
        onSubmit={app.handleAuth}
        onLogout={app.logout}
      />

      <SchoolModal
        open={app.showSchoolModal}
        token={app.token}
        schools={app.schools}
        selectedSchoolId={app.selectedSchoolId}
        currentSchool={app.currentSchool}
        onClose={() => app.setShowSchoolModal(false)}
        onSelectSchool={app.setSelectedSchoolId}
      />

      <CreateCourseModal
        open={app.showCreateCourseModal}
        currentSchool={app.currentSchool}
        onClose={() => app.setShowCreateCourseModal(false)}
        onSubmit={async (payload) => {
          const data = await app.createCourse(payload);
          if (data) {
            app.setShowCreateCourseModal(false);
            return true;
          }
          return false;
        }}
      />

      <CompleteCourseModal
        open={app.showCompleteCourseModal}
        currentCourse={app.currentCourse}
        onClose={() => app.setShowCompleteCourseModal(false)}
        onConfirm={app.completeCurrentCourse}
      />
    </div>
  );
}

"use client";

import { useParams } from "next/navigation";
import { doc, onSnapshot, getDoc } from "firebase/firestore";
import { db } from "@/lib/firebase";
import { useEffect, useState } from "react";
import { Quiz, UserProfile } from "@/lib/types";
import { Card } from "@/components/ui/card";
import { formatDate } from "./_components/shared";
import { Users, TrendingUp, Trophy, BarChart3, Crown } from "lucide-react";
import Image from "next/image";

export default function QuizOverviewPage() {
  const params = useParams();
  const quizId = params.id as string;
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [userProfiles, setUserProfiles] = useState<Record<string, UserProfile>>(
    {}
  );

  useEffect(() => {
    if (!quizId) return;
    const unsubscribe = onSnapshot(doc(db, "quizzes", quizId), (doc) => {
      if (doc.exists()) {
        setQuiz({ id: doc.id, ...doc.data() } as Quiz);
      }
    });
    return () => unsubscribe();
  }, [quizId]);

  // Fetch user profiles for non-anonymous top performers
  useEffect(() => {
    if (!quiz?.topPerformers) return;
    const fetchProfiles = async () => {
      const profiles: Record<string, UserProfile> = {};
      for (const performer of quiz.topPerformers || []) {
        if (!performer.isAnonymous && !userProfiles[performer.userId]) {
          try {
            const userDoc = await getDoc(doc(db, "users", performer.userId));
            if (userDoc.exists()) {
              profiles[performer.userId] = userDoc.data() as UserProfile;
            }
          } catch (error) {
            console.error("Error fetching user profile:", error);
          }
        }
      }
      setUserProfiles((prev) => ({ ...prev, ...profiles }));
    };
    fetchProfiles();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quiz?.topPerformers]);

  if (!quiz) return null;

  // Use metrics from quiz document
  const metrics = quiz.metrics || {
    totalResponses: 0,
    avgScore: 0,
    highestScore: 0,
    lowestScore: 0,
    scoreDistribution: [0, 0, 0, 0, 0],
  };
  const topPerformers = quiz.topPerformers || [];
  const scoreDistribution = metrics.scoreDistribution || [0, 0, 0, 0, 0];

  return (
    <div className="space-y-6">
      {/* Stats Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-full">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold">{metrics.totalResponses}</p>
              <p className="text-sm text-muted-foreground">Respondents</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-full">
              <TrendingUp className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold">
                {metrics.avgScore.toFixed(1)}%
              </p>
              <p className="text-sm text-muted-foreground">Avg Score</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-full">
              <Trophy className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold">
                {metrics.highestScore.toFixed(1)}%
              </p>
              <p className="text-sm text-muted-foreground">Highest</p>
            </div>
          </div>
        </Card>
        <Card className="p-4">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-full">
              <BarChart3 className="w-5 h-5" />
            </div>
            <div>
              <p className="text-2xl font-bold">
                {metrics.lowestScore.toFixed(1)}%
              </p>
              <p className="text-sm text-muted-foreground">Lowest</p>
            </div>
          </div>
        </Card>
      </div>

      {/* Score Distribution & Top Performers */}
      <div className="grid md:grid-cols-2 gap-6">
        <Card className="p-6">
          <h3 className="font-semibold mb-4">Score Distribution</h3>
          {metrics.totalResponses === 0 ? (
            <p className="text-muted-foreground text-center py-8">
              No responses yet
            </p>
          ) : (
            <div className="relative h-64">
              <div className="absolute inset-0 flex items-end justify-between gap-2 px-4">
                {[
                  {
                    label: "0-29%",
                    count: scoreDistribution[0],
                    color: "bg-error",
                  },
                  {
                    label: "30-49%",
                    count: scoreDistribution[1],
                    color: "bg-destructive",
                  },
                  {
                    label: "50-69%",
                    count: scoreDistribution[2],
                    color: "bg-warning",
                  },
                  {
                    label: "70-89%",
                    count: scoreDistribution[3],
                    color: "bg-success",
                  },
                  {
                    label: "90-100%",
                    count: scoreDistribution[4],
                    color: "bg-success",
                  },
                ].map((range) => {
                  const heightPercent =
                    metrics.totalResponses > 0
                      ? (range.count / metrics.totalResponses) * 100
                      : 0;
                  return (
                    <div
                      key={range.label}
                      className="flex-1 flex flex-col items-center gap-2"
                    >
                      <div className="relative w-full group">
                        <div
                          className={`w-full ${range.color} rounded-t-lg transition-all duration-300 hover:opacity-80 relative`}
                          style={{
                            height: `${Math.max(heightPercent * 2, 4)}px`,
                          }}
                        >
                          {range.count > 0 && (
                            <div className="absolute -top-6 left-1/2 transform -translate-x-1/2 text-xs font-bold whitespace-nowrap">
                              {range.count}
                            </div>
                          )}
                        </div>
                      </div>
                      <div className="text-center">
                        <p className="text-xs font-medium">{range.label}</p>
                        <p className="text-xs text-muted-foreground">
                          {(
                            (range.count / metrics.totalResponses) *
                            100
                          ).toFixed(0)}
                          %
                        </p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Card>

        <Card className="p-6">
          <h3 className="font-semibold mb-4 flex items-center gap-2">
            <Crown className="w-5 h-5 text-warning" />
            Top Performers
          </h3>
          {topPerformers.length === 0 ? (
            <p className="text-muted-foreground text-center py-8">
              No responses yet
            </p>
          ) : (
            <div className="space-y-3">
              {topPerformers.map((attempt, idx) => {
                const firstLetter =
                  attempt.displayName?.[0]?.toUpperCase() || "A";
                const userProfile = userProfiles[attempt.userId];
                const showPhoto = !attempt.isAnonymous && userProfile?.photoURL;

                return (
                  <div
                    key={idx}
                    className="flex items-center gap-3 p-3 rounded-lg bg-zinc-50 dark:bg-zinc-800/50"
                  >
                    {showPhoto ? (
                      <Image
                        src={userProfile.photoURL!}
                        alt={attempt.displayName}
                        width={32}
                        height={32}
                        className="w-8 h-8 rounded-full"
                        unoptimized
                      />
                    ) : (
                      <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center font-semibold text-sm text-primary">
                        {firstLetter}
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="font-medium truncate">
                        {attempt.displayName}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {formatDate(attempt.attemptAt)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-bold text-success">
                        {attempt.score.toFixed(1)}%
                      </p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

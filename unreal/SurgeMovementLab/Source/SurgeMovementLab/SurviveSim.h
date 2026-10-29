#pragma once
// Original bounded math shared by the Unreal game and portable C++ checks.
// No engine types, global state, allocations, frame clocks or client authority.
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace SurviveSim
{
    struct Vec2 { double X = 0; double Y = 0; };
    struct Rect { double MinX; double MinY; double MaxX; double MaxY; };
    struct Path { std::array<Vec2, 34> Points{}; std::size_t Count = 0; };
    inline constexpr double ArenaHalfExtent = 1300.;
    inline constexpr std::array<Rect, 2> ArenaObstacles{{
        {-520., -430., -280., -70.}, {300., 240., 580., 480.}
    }};

    inline bool Finite(Vec2 Point) { return std::isfinite(Point.X) && std::isfinite(Point.Y); }
    inline bool ValidRadius(double Radius)
    {
        return std::isfinite(Radius) && Radius >= 0. && Radius < ArenaHalfExtent;
    }
    inline Rect Expanded(Rect Box, double Radius)
    {
        return {Box.MinX - Radius, Box.MinY - Radius, Box.MaxX + Radius, Box.MaxY + Radius};
    }
    inline bool Contains(Rect Box, Vec2 Point)
    {
        return Point.X >= Box.MinX && Point.X <= Box.MaxX && Point.Y >= Box.MinY && Point.Y <= Box.MaxY;
    }
    inline bool IsWalkable(Vec2 Point, double Radius)
    {
        if (!Finite(Point) || !ValidRadius(Radius) || std::abs(Point.X) >= ArenaHalfExtent - Radius ||
            std::abs(Point.Y) >= ArenaHalfExtent - Radius) return false;
        for (const auto& Box : ArenaObstacles) if (Contains(Expanded(Box, Radius), Point)) return false;
        return true;
    }
    inline bool SegmentClear(Vec2 From, Vec2 To, double Radius)
    {
        if (!IsWalkable(From, Radius) || !IsWalkable(To, Radius)) return false;
        for (const auto& Obstacle : ArenaObstacles)
        {
            const auto Box = Expanded(Obstacle, Radius);
            double MinT = 0., MaxT = 1.;
            bool Intersects = true;
            for (unsigned Axis = 0; Axis < 2; ++Axis)
            {
                const double Start = Axis == 0 ? From.X : From.Y;
                const double Step = Axis == 0 ? To.X - From.X : To.Y - From.Y;
                const double Low = Axis == 0 ? Box.MinX : Box.MinY;
                const double High = Axis == 0 ? Box.MaxX : Box.MaxY;
                if (std::abs(Step) < 1e-12)
                {
                    if (Start < Low || Start > High) { Intersects = false; break; }
                    continue;
                }
                double A = (Low - Start) / Step, B = (High - Start) / Step;
                if (A > B) { const double Swap = A; A = B; B = Swap; }
                if (A > MinT) MinT = A;
                if (B < MaxT) MaxT = B;
                if (MinT > MaxT) { Intersects = false; break; }
            }
            if (Intersects) return false;
        }
        return true;
    }
    inline bool FindPath(Vec2 From, Vec2 To, double Radius, Path& Output)
    {
        Output.Count = 0;
        if (!IsWalkable(From, Radius) || !IsWalkable(To, Radius)) return false;
        constexpr std::size_t NodeCount = 2 + 4 * ArenaObstacles.size();
        static_assert(NodeCount <= 34, "Bounded arena graph capacity exceeded");
        std::array<Vec2, NodeCount> Nodes{};
        Nodes[0] = From;
        Nodes[1] = To;
        std::size_t NextNode = 2;
        for (const auto& Obstacle : ArenaObstacles)
        {
            const auto Box = Expanded(Obstacle, Radius + 2.);
            Nodes[NextNode++] = {Box.MinX, Box.MinY};
            Nodes[NextNode++] = {Box.MinX, Box.MaxY};
            Nodes[NextNode++] = {Box.MaxX, Box.MaxY};
            Nodes[NextNode++] = {Box.MaxX, Box.MinY};
        }
        const double Infinity = std::numeric_limits<double>::infinity();
        std::array<double, NodeCount> Cost{};
        std::array<std::size_t, NodeCount> Parent{};
        std::array<bool, NodeCount> Visited{};
        Cost.fill(Infinity);
        Parent.fill(NodeCount);
        Cost[0] = 0.;
        for (std::size_t Iteration = 0; Iteration < NodeCount; ++Iteration)
        {
            std::size_t Best = NodeCount;
            for (std::size_t I = 0; I < NodeCount; ++I)
                if (!Visited[I] && (Best == NodeCount || Cost[I] < Cost[Best])) Best = I;
            if (Best == NodeCount || !std::isfinite(Cost[Best])) return false;
            if (Best == 1) break;
            Visited[Best] = true;
            for (std::size_t Next = 0; Next < NodeCount; ++Next)
            {
                if (Visited[Next] || Next == Best || !SegmentClear(Nodes[Best], Nodes[Next], Radius)) continue;
                const double Candidate = Cost[Best] + std::hypot(Nodes[Next].X - Nodes[Best].X, Nodes[Next].Y - Nodes[Best].Y);
                if (Candidate < Cost[Next]) { Cost[Next] = Candidate; Parent[Next] = Best; }
            }
        }
        if (Parent[1] == NodeCount) return false;
        std::array<Vec2, NodeCount> Reverse{};
        std::size_t Count = 0;
        for (std::size_t Index = 1; Index != 0; Index = Parent[Index])
        {
            if (Index >= NodeCount || Count >= NodeCount) return false;
            Reverse[Count++] = Nodes[Index];
        }
        while (Count) Output.Points[Output.Count++] = Reverse[--Count];
        return true;
    }
    inline double ClampDashDistance(double Requested, double Minimum, double Maximum)
    {
        if (!std::isfinite(Requested) || !std::isfinite(Minimum) || !std::isfinite(Maximum) ||
            Requested <= 0. || Minimum < 0. || Maximum < Minimum) return 0.;
        return Requested < Minimum ? Minimum : Requested > Maximum ? Maximum : Requested;
    }
    inline double DashDistanceAt(double Elapsed, double Distance, double Speed)
    {
        if (!std::isfinite(Elapsed) || !std::isfinite(Distance) || !std::isfinite(Speed) ||
            Elapsed < 0. || Distance <= 0. || Speed <= 0.) return 0.;
        if (Elapsed == 0.) return 0.;
        // Compare time before multiplication to keep even large finite inputs bounded.
        return Elapsed >= Distance / Speed ? Distance : Elapsed * Speed;
    }
    inline double RelativeClearance(Vec2 ProjectileBefore, Vec2 ProjectileAfter,
        Vec2 PlayerBefore, Vec2 PlayerAfter, double CombinedRadius)
    {
        if (!Finite(ProjectileBefore) || !Finite(ProjectileAfter) || !Finite(PlayerBefore) || !Finite(PlayerAfter) ||
            !std::isfinite(CombinedRadius) || CombinedRadius < 0.) return std::numeric_limits<double>::infinity();
        const Vec2 Start{ProjectileBefore.X - PlayerBefore.X, ProjectileBefore.Y - PlayerBefore.Y};
        const Vec2 End{ProjectileAfter.X - PlayerAfter.X, ProjectileAfter.Y - PlayerAfter.Y};
        const Vec2 Delta{End.X - Start.X, End.Y - Start.Y};
        const double Denominator = Delta.X * Delta.X + Delta.Y * Delta.Y;
        double Alpha = Denominator > 0. ? -(Start.X * Delta.X + Start.Y * Delta.Y) / Denominator : 0.;
        Alpha = Alpha < 0. ? 0. : Alpha > 1. ? 1. : Alpha;
        const double Distance = std::hypot(Start.X + Delta.X * Alpha, Start.Y + Delta.Y * Alpha);
        return std::isfinite(Distance) ? Distance - CombinedRadius : std::numeric_limits<double>::infinity();
    }
    struct CaptureBudget
    {
        static constexpr std::uint64_t MaxRows = 10000;
        static constexpr std::uint64_t MaxBytes = 4 * 1024 * 1024;
        static constexpr std::uint64_t TerminalReserve = 2048;
        static bool CanWrite(bool Terminal, std::uint64_t Rows, std::uint64_t Bytes, std::uint64_t NextBytes)
        {
            const std::uint64_t RowLimit = Terminal ? MaxRows : MaxRows - 1;
            const std::uint64_t ByteLimit = Terminal ? MaxBytes : MaxBytes - TerminalReserve;
            return Rows < RowLimit && Bytes <= ByteLimit && NextBytes <= ByteLimit - Bytes;
        }
    };
}

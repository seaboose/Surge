#include "../Source/SurgeMovementLab/SurviveSim.h"

#include <array>
#include <cmath>
#include <cstdint>
#include <iostream>
#include <limits>
#include <string>

namespace
{
int Checks = 0;
int Failures = 0;

void Check(bool condition, const std::string& label)
{
    ++Checks;
    if (!condition)
    {
        ++Failures;
        std::cerr << "FAIL: " << label << '\n';
    }
}

bool Near(double actual, double expected, double tolerance = 1.e-8)
{
    return std::isfinite(actual) && std::abs(actual - expected) <= tolerance;
}

bool Same(SurviveSim::Vec2 a, SurviveSim::Vec2 b)
{
    return Near(a.X, b.X) && Near(a.Y, b.Y);
}

// An independent, sampled geometric oracle supplements SegmentClear. It does
// not implement a second pathfinder or a second swept-collision algorithm.
bool SampledSegmentAvoidsArenaSolids(SurviveSim::Vec2 a, SurviveSim::Vec2 b, double radius)
{
    for (int step = 0; step <= 128; ++step)
    {
        const double t = static_cast<double>(step) / 128.;
        const SurviveSim::Vec2 point{a.X + (b.X - a.X) * t, a.Y + (b.Y - a.Y) * t};
        if (std::abs(point.X) >= 1300. - radius || std::abs(point.Y) >= 1300. - radius)
            return false;
        // Fixed authored arena rectangles, independently recorded by the test.
        const std::array<SurviveSim::Rect, 2> solids{{
            {-520., -430., -280., -70.}, {300., 240., 580., 480.}
        }};
        for (const auto& box : solids)
            if (point.X >= box.MinX - radius && point.X <= box.MaxX + radius &&
                point.Y >= box.MinY - radius && point.Y <= box.MaxY + radius)
                return false;
    }
    return true;
}

void CheckRoute(SurviveSim::Vec2 from, SurviveSim::Vec2 to, double radius,
                bool needsDetour, const std::string& name)
{
    SurviveSim::Path route{};
    const bool found = SurviveSim::FindPath(from, to, radius, route);
    Check(found, name + ": route found");
    Check(route.Count > 0 && route.Count <= route.Points.size(), name + ": bounded nonempty route");
    if (!found || route.Count == 0 || route.Count > route.Points.size()) return;
    Check(Same(route.Points[route.Count - 1], to), name + ": route ends at requested goal");
    Check(needsDetour ? route.Count >= 3 : route.Count == 1, name + ": expected corner count");
    auto previous = from;
    for (std::size_t i = 0; i < route.Count; ++i)
    {
        Check(SurviveSim::IsWalkable(route.Points[i], radius), name + ": corner is walkable");
        Check(SurviveSim::SegmentClear(previous, route.Points[i], radius), name + ": segment is clear");
        Check(SampledSegmentAvoidsArenaSolids(previous, route.Points[i], radius),
              name + ": independently sampled segment avoids both expanded obstacles and walls");
        previous = route.Points[i];
    }
}

void CheckPaths()
{
    using namespace SurviveSim;
    Check(Near(ArenaHalfExtent, 1300.), "authored arena extent");
    Check(ArenaObstacles.size() == 2, "two authored obstacles");
    Check(Near(ArenaObstacles[0].MinX, -520.) && Near(ArenaObstacles[0].MinY, -430.) &&
          Near(ArenaObstacles[0].MaxX, -280.) && Near(ArenaObstacles[0].MaxY, -70.), "west authored obstacle");
    Check(Near(ArenaObstacles[1].MinX, 300.) && Near(ArenaObstacles[1].MinY, 240.) &&
          Near(ArenaObstacles[1].MaxX, 580.) && Near(ArenaObstacles[1].MaxY, 480.), "east authored obstacle");
    CheckRoute({0., -650.}, {0., 650.}, 41., false, "open vertical route");
    CheckRoute({-700., -250.}, {-100., -250.}, 41., true, "west obstacle detour");
    CheckRoute({150., 360.}, {750., 360.}, 65., true, "east obstacle detour at damage-sized radius");
    CheckRoute({-100., -250.}, {-700., -250.}, 41., true, "reverse west detour");
    CheckRoute({-800., -700.}, {850., 850.}, 41., true, "route detours around both obstacles");
    CheckRoute({0., 0.}, {0., 0.}, 41., false, "stationary route");

    Check(!SegmentClear({-700., -250.}, {-100., -250.}, 41.), "west direct chord blocked");
    Check(!SegmentClear({150., 360.}, {750., 360.}, 41.), "east direct chord blocked");
    Check(SegmentClear({-700., -460.}, {-100., -460.}, 20.), "small radius passes obstacle clearance");
    Check(!SegmentClear({-700., -460.}, {-100., -460.}, 41.), "larger radius blocks same chord");
    Check(!SegmentClear({-700., -471.}, {-100., -471.}, 41.), "expanded obstacle tangency conservatively blocked");
    Check(IsWalkable({-550., -250.}, 20.), "small radius fits near obstacle");
    Check(!IsWalkable({-550., -250.}, 41.), "path radius blocks same point");
    Check(IsWalkable({1280., 0.}, 10.), "small radius fits near outer wall");
    Check(!IsWalkable({1280., 0.}, 41.), "path radius blocks wall-adjacent point");
    Check(!IsWalkable({1259., 0.}, 41.), "closed outer wall boundary blocked");
    Check(!IsWalkable({-561., -250.}, 41.), "closed expanded obstacle edge blocked");
    Check(IsWalkable({0., 0.}, 0.), "zero radius is valid");
    Check(!SegmentClear({0., 0.}, {1400., 0.}, 41.), "segment outside arena rejected");
    Check(!SegmentClear({-400., -250.}, {0., 0.}, 41.), "segment with solid endpoint rejected");

    Path rejected{};
    rejected.Count = 7;
    Check(!FindPath({0., -650.}, {-400., -250.}, 41., rejected) && rejected.Count == 0,
          "solid destination rejected and stale route cleared");
    rejected.Count = 7;
    Check(!FindPath({-400., -250.}, {0., 0.}, 41., rejected) && rejected.Count == 0,
          "solid start rejected and stale route cleared");
    rejected.Count = 7;
    Check(!FindPath({0., 0.}, {1400., 0.}, 41., rejected) && rejected.Count == 0,
          "outside destination rejected and stale route cleared");

    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double infinity = std::numeric_limits<double>::infinity();
    const std::array<Vec2, 6> invalidPoints{{{nan, 0.}, {0., nan}, {infinity, 0.},
                                          {0., infinity}, {-infinity, 0.}, {0., -infinity}}};
    for (const auto point : invalidPoints)
    {
        Check(!IsWalkable(point, 41.), "nonfinite point rejected by walkability");
        Check(!SegmentClear(point, {0., 0.}, 41.) && !SegmentClear({0., 0.}, point, 41.),
              "nonfinite segment endpoint rejected");
        rejected.Count = 7;
        Check(!FindPath(point, {0., 0.}, 41., rejected) && rejected.Count == 0,
              "nonfinite start rejects and clears path");
        rejected.Count = 7;
        Check(!FindPath({0., 0.}, point, 41., rejected) && rejected.Count == 0,
              "nonfinite goal rejects and clears path");
    }
    for (double radius : std::array<double, 5>{{-1., nan, infinity, -infinity, 1300.}})
    {
        Check(!IsWalkable({0., 0.}, radius), "invalid radius rejects walkability");
        Check(!SegmentClear({0., 0.}, {0., 100.}, radius), "invalid radius rejects segment");
        rejected.Count = 7;
        Check(!FindPath({0., 0.}, {0., 100.}, radius, rejected) && rejected.Count == 0,
              "invalid radius rejects and clears path");
    }
}

void CheckDashes()
{
    using namespace SurviveSim;
    Check(Near(ClampDashDistance(10., 200., 425.), 200.), "dash clamps up to minimum");
    Check(Near(ClampDashDistance(300., 200., 425.), 300.), "dash preserves interior request");
    Check(Near(ClampDashDistance(900., 200., 425.), 425.), "dash clamps down to maximum");
    Check(Near(ClampDashDistance(200., 200., 425.), 200.), "dash minimum boundary");
    Check(Near(ClampDashDistance(425., 200., 425.), 425.), "dash maximum boundary");
    Check(Near(ClampDashDistance(0., 200., 425.), 0.), "zero aim distance rejected");
    Check(Near(ClampDashDistance(-1., 200., 425.), 0.), "negative aim distance rejected");
    Check(Near(DashDistanceAt(0., 425., 1350.), 0.), "dash starts at zero");
    Check(Near(DashDistanceAt(.01, 425., 1350.), 13.5), "dash fixed speed after 10ms");
    Check(Near(DashDistanceAt(.1, 425., 1350.), 135.), "dash fixed speed after 100ms");
    Check(Near(DashDistanceAt(200. / 1350., 200., 1350.), 200.), "minimum dash exact duration");
    Check(Near(DashDistanceAt(425. / 1350., 425., 1350.), 425.), "maximum dash exact duration");
    Check(Near(DashDistanceAt(100., 425., 1350.), 425.), "dash never overshoots range");
    Check(Near(DashDistanceAt(.2, 0., 1350.), 0.), "zero permitted distance stays zero");
    Check(Near(DashDistanceAt(0., std::numeric_limits<double>::denorm_min(),
                              std::numeric_limits<double>::max()), 0.),
          "zero elapsed stays zero even if finite dash duration underflows");
    Check(Near(DashDistanceAt(std::numeric_limits<double>::max(), 425.,
                              std::numeric_limits<double>::max()), 425.),
          "extreme finite time and speed cannot overflow capped dash distance");

    const std::array<double, 8> partitions{{1. / 120., .011, .037, .004, .08, .025, .1, .2}};
    double elapsed = 0.;
    double accumulated = 0.;
    double previous = 0.;
    for (const double step : partitions)
    {
        elapsed += step;
        const double current = DashDistanceAt(elapsed, 425., 1350.);
        const double movement = current - previous;
        Check(movement >= -1.e-8 && movement <= 1350. * step + 1.e-8,
              "partitioned dash advances by no more than fixed speed");
        accumulated += movement;
        previous = current;
    }
    Check(Near(accumulated, 425.) && Near(accumulated, DashDistanceAt(elapsed, 425., 1350.)),
          "uneven frame partition reaches identical capped dash distance");

    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double infinity = std::numeric_limits<double>::infinity();
    for (double value : std::array<double, 3>{{nan, infinity, -infinity}})
    {
        Check(Near(ClampDashDistance(value, 200., 425.), 0.), "nonfinite dash request rejected");
        Check(Near(ClampDashDistance(300., value, 425.), 0.), "nonfinite minimum rejected");
        Check(Near(ClampDashDistance(300., 200., value), 0.), "nonfinite maximum rejected");
        Check(Near(DashDistanceAt(value, 425., 1350.), 0.), "nonfinite elapsed rejected");
        Check(Near(DashDistanceAt(.1, value, 1350.), 0.), "nonfinite distance rejected");
        Check(Near(DashDistanceAt(.1, 425., value), 0.), "nonfinite speed rejected");
    }
    Check(Near(ClampDashDistance(300., -1., 425.), 0.), "negative minimum rejected");
    Check(Near(ClampDashDistance(300., 425., 200.), 0.), "reversed range rejected");
    Check(Near(DashDistanceAt(-.1, 425., 1350.), 0.), "negative elapsed rejected");
    Check(Near(DashDistanceAt(.1, -1., 1350.), 0.), "negative distance rejected");
    Check(Near(DashDistanceAt(.1, 425., 0.), 0.), "zero speed rejected");
    Check(Near(DashDistanceAt(.1, 425., -1.), 0.), "negative speed rejected");
}

void CheckSweeps()
{
    using namespace SurviveSim;
    Check(Near(RelativeClearance({-10., 0.}, {10., 0.}, {0., 0.}, {0., 0.}, 2.), -2.),
          "projectile swept crossing hits between endpoints");
    Check(Near(RelativeClearance({-10., 0.}, {10., 0.}, {0., -10.}, {0., 10.}, 2.), -2.),
          "simultaneously moving player and projectile cross");
    Check(Near(RelativeClearance({-10., 2.}, {10., 2.}, {0., 0.}, {0., 0.}, 2.), 0.),
          "tangent clearance is exactly zero");
    Check(Near(RelativeClearance({-10., 3.}, {10., 3.}, {0., 0.}, {0., 0.}, 2.), 1.),
          "near miss has positive clearance");
    Check(Near(RelativeClearance({3., 4.}, {3., 4.}, {0., 0.}, {0., 0.}, 2.), 3.),
          "stationary pair avoids zero-length division");
    Check(Near(RelativeClearance({0., 5.}, {10., 5.}, {0., 0.}, {10., 0.}, 2.), 3.),
          "equal parallel velocities retain separation");
    Check(Near(RelativeClearance({4., 0.}, {10., 0.}, {0., 0.}, {0., 0.}, 2.), 2.),
          "closest point clamped to interval start");
    Check(Near(RelativeClearance({10., 0.}, {4., 0.}, {0., 0.}, {0., 0.}, 2.), 2.),
          "closest point clamped to interval end");
    Check(Near(RelativeClearance({-10., 0.}, {10., 0.}, {0., 0.}, {0., 0.}, 0.), 0.),
          "zero combined radius remains valid");

    // A blink is discontinuous: the caller supplies its landing point for BOTH
    // player endpoints. The helper does not decide whether movement is a blink.
    Check(Near(RelativeClearance({0., 0.}, {0., 0.}, {10., 0.}, {10., 0.}, 2.), 8.),
          "blink landing outside threat does not sweep teleport chord");
    Check(Near(RelativeClearance({0., 0.}, {0., 0.}, {-10., 0.}, {10., 0.}, 2.), -2.),
          "continuous movement across same chord would hit");
    Check(Near(RelativeClearance({0., 0.}, {0., 0.}, {0., 0.}, {0., 0.}, 2.), -2.),
          "blink landing inside threat still hits");

    const double nan = std::numeric_limits<double>::quiet_NaN();
    const double infinity = std::numeric_limits<double>::infinity();
    for (double invalid : std::array<double, 3>{{nan, infinity, -infinity}})
    {
        Check(RelativeClearance({invalid, 0.}, {1., 0.}, {0., 0.}, {0., 0.}, 2.) == infinity,
              "invalid projectile start returns unavailable sentinel");
        Check(RelativeClearance({0., 0.}, {0., invalid}, {0., 0.}, {0., 0.}, 2.) == infinity,
              "invalid projectile end returns unavailable sentinel");
        Check(RelativeClearance({0., 0.}, {1., 0.}, {invalid, 0.}, {0., 0.}, 2.) == infinity,
              "invalid player start returns unavailable sentinel");
        Check(RelativeClearance({0., 0.}, {1., 0.}, {0., 0.}, {0., invalid}, 2.) == infinity,
              "invalid player end returns unavailable sentinel");
        Check(RelativeClearance({0., 0.}, {1., 0.}, {0., 0.}, {0., 0.}, invalid) == infinity,
              "invalid combined radius returns unavailable sentinel");
    }
    Check(RelativeClearance({0., 0.}, {1., 0.}, {0., 0.}, {0., 0.}, -1.) == infinity,
          "negative combined radius rejected");
}

void CheckCaptureBudgets()
{
    using SurviveSim::CaptureBudget;
    constexpr std::uint64_t Rows = 10000;
    constexpr std::uint64_t Bytes = 4 * 1024 * 1024;
    constexpr std::uint64_t Reserve = 2048;
    Check(CaptureBudget::MaxRows == Rows && CaptureBudget::MaxBytes == Bytes &&
          CaptureBudget::TerminalReserve == Reserve, "capture contract constants");
    Check(CaptureBudget::CanWrite(false, 0, 0, 100), "ordinary initial row allowed");
    Check(CaptureBudget::CanWrite(false, Rows - 2, 0, 100), "ordinary penultimate row allowed");
    Check(!CaptureBudget::CanWrite(false, Rows - 1, 0, 100), "ordinary row preserves one terminal slot");
    Check(CaptureBudget::CanWrite(true, Rows - 1, 0, 100), "terminal row may use final row slot");
    Check(!CaptureBudget::CanWrite(true, Rows, 0, 100), "terminal cannot exceed row cap");
    Check(!CaptureBudget::CanWrite(false, Rows, 0, 100), "ordinary cannot exceed row cap");
    Check(CaptureBudget::CanWrite(false, 0, Bytes - Reserve - 100, 100),
          "ordinary write exactly reaches reserved-byte boundary");
    Check(!CaptureBudget::CanWrite(false, 0, Bytes - Reserve - 100, 101),
          "ordinary write cannot consume terminal byte reserve");
    Check(CaptureBudget::CanWrite(true, 0, Bytes - Reserve, Reserve),
          "terminal write may consume reserve exactly");
    Check(CaptureBudget::CanWrite(true, 0, Bytes - 100, 100), "terminal exact total-byte boundary");
    Check(!CaptureBudget::CanWrite(true, 0, Bytes - 100, 101), "terminal byte overflow rejected");
    Check(!CaptureBudget::CanWrite(false, 0, Bytes + 1, 1), "invalid existing ordinary byte count rejected");
    Check(!CaptureBudget::CanWrite(true, 0, Bytes + 1, 1), "invalid existing terminal byte count rejected");
    Check(!CaptureBudget::CanWrite(false, Rows + 1, 0, 1), "invalid existing ordinary row count rejected");
    Check(!CaptureBudget::CanWrite(true, Rows + 1, 0, 1), "invalid existing terminal row count rejected");
    const auto maximum = std::numeric_limits<std::uint64_t>::max();
    for (bool terminal : std::array<bool, 2>{{false, true}})
    {
        Check(!CaptureBudget::CanWrite(terminal, maximum, 0, 1), "uint64 row overflow rejected");
        Check(!CaptureBudget::CanWrite(terminal, 0, maximum, 1), "uint64 existing byte overflow rejected");
        Check(!CaptureBudget::CanWrite(terminal, 0, 1, maximum), "uint64 appended byte overflow rejected");
        Check(!CaptureBudget::CanWrite(terminal, 0, maximum, maximum), "uint64 wraparound rejected");
    }
}
}

int main()
{
    CheckPaths();
    CheckDashes();
    CheckSweeps();
    CheckCaptureBudgets();
    std::cout << "Survive portable shared-math checks: " << Checks << " checks, " << Failures << " failures.\n";
    std::cout << "Scope: shared C++17 math only; no Unreal/UHT compilation, runtime integration, or playtest proof.\n";
    return Failures == 0 ? 0 : 1;
}

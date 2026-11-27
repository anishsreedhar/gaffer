//////////////////////////////////////////////////////////////////////////
//
//  Copyright (c) 2025, Cinesite VFX Ltd. All rights reserved.
//
//  Redistribution and use in source and binary forms, with or without
//  modification, are permitted provided that the following conditions are
//  met:
//
//     * Redistributions of source code must retain the above copyright
//       notice, this list of conditions and the following disclaimer.
//
//     * Redistributions in binary form must reproduce the above copyright
//       notice, this list of conditions and the following disclaimer in the
//       documentation and/or other materials provided with the distribution.
//
//     * Neither the name of Image Engine Design nor the names of any
//       other contributors to this software may be used to endorse or
//       promote products derived from this software without specific prior
//       written permission.
//
//  THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS
//  IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
//  THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
//  PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR
//  CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
//  EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
//  PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
//  PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
//  LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
//  NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
//  SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
//
//////////////////////////////////////////////////////////////////////////

#pragma once

#include "SceneAlgo.h"

IECORE_PUSH_DEFAULT_VISIBILITY
#include "scene/light.h"
IECORE_POP_DEFAULT_VISIBILITY

namespace IECoreCycles::LightAlgo
{

// Scene files use Gaffer's light names. Cycles 5.3 uses a separate concrete
// geometry class for each type; disk, quad and portal all use AreaLight.
struct LightType
{
	const char *name;
	ccl::LightType type;
	const ccl::NodeType *nodeType;
	ccl::Light *( *create )( ccl::Scene * );
};

template<typename T>
LightType lightType( const char *name, ccl::LightType type )
{
	return { name, type, T::get_node_type(), []( ccl::Scene *scene ) -> ccl::Light * { return SceneAlgo::createNodeWithLock<T>( scene ); } };
}

inline const auto &types()
{
	static const LightType types[] = {
		lightType<ccl::PointLight>( "point_light", ccl::LIGHT_POINT ),
		lightType<ccl::SpotLight>( "spot_light", ccl::LIGHT_SPOT ),
		lightType<ccl::SunLight>( "distant_light", ccl::LIGHT_SUN ),
		lightType<ccl::BackgroundLight>( "background_light", ccl::LIGHT_BACKGROUND ),
		lightType<ccl::AreaLight>( "quad_light", ccl::LIGHT_AREA ),
		lightType<ccl::AreaLight>( "disk_light", ccl::LIGHT_AREA ),
		lightType<ccl::AreaLight>( "portal", ccl::LIGHT_AREA ),
	};
	return types;
}

inline const LightType &type( const std::string &name )
{
	for( const auto &type : types() )
	{
		if( name == type.name )
		{
			return type;
		}
	}
	return types()[0];
}

} // namespace IECoreCycles::LightAlgo
